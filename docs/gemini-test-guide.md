# Hướng dẫn cấu hình và test Gemini cho E3

Dành cho thành viên team cần chạy E3 (trích xuất tín hiệu, viết lý do) với Gemini thật trên project Google Cloud `ai-codguard`. Thiết kế E3 xem [e3-ai.md](e3-ai.md); Live API cho cuộc gọi (E5) xem [gemini-live.md](gemini-live.md).

Kiểm tra lần cuối ngày 12/10/2026. Các lệnh `gcloud` và lần chạy live chưa được chạy thử trên `ai-codguard`. Người chạy đầu tiên hãy sửa file này nếu thấy sai khác.

## Tóm tắt

- Backend **không dùng API key**. E3 gọi Gemini qua Gemini Enterprise Agent Platform (tên cũ: Vertex AI) bằng **Application Default Credentials (ADC)**: khi chạy local là tài khoản Google của bạn, khi chạy trên Cloud Run là service account.
- Cần 4 thứ: API `aiplatform.googleapis.com` đã bật, role `roles/aiplatform.user`, ADC trên máy, và 2 biến `GOOGLE_CLOUD_PROJECT`, `GEMINI_MODEL`.
- Test từ rẻ đến đắt: unit test → smoke test 1 request → 1 đơn qua code E3 → eval 30 đơn.
- **Rủi ro cần kiểm tra trước:** code E3 cố định region `asia-southeast1`, nhưng trang model của Google ghi các model Flash mới chỉ bán pay-as-you-go ở `global`, `us`, `eu`. Smoke test ở bước 5.2 sẽ cho biết có gọi được không (mục 4).

## 1. Code đang gọi Gemini như thế nào

[`backend/scoring/ai/client.py`](../backend/scoring/ai/client.py) tạo client như sau:

```python
genai.Client(enterprise=True, project=GOOGLE_CLOUD_PROJECT, location="asia-southeast1")
```

| Điểm | Ý nghĩa khi test |
|---|---|
| Endpoint | `https://asia-southeast1-aiplatform.googleapis.com` |
| Xác thực | ADC. SDK bỏ qua `GOOGLE_API_KEY` / `GEMINI_API_KEY` vì code đã truyền `project` và `location` |
| Region | Hằng số `TEXT_LOCATION` trong code. Đổi `GOOGLE_CLOUD_REGION` hay `GOOGLE_CLOUD_LOCATION` **không** đổi region của E3 |
| Biến E3 đọc | `GOOGLE_CLOUD_PROJECT`, `GEMINI_MODEL`, `GEMINI_TIMEOUT_SECONDS` (mặc định 10), `GEMINI_MAX_CALLS` (mặc định 100) |
| Thiếu `GOOGLE_CLOUD_PROJECT` hoặc `GEMINI_MODEL` | Không gọi Gemini và **không báo lỗi**: tín hiệu AI rỗng, gateway ghi event `unavailable` |
| Lỗi SDK (auth, quyền, model) | Code giấu message để log không chứa dữ liệu người mua, chỉ ghi event `error`. Muốn xem lỗi thật thì chạy smoke test ở bước 5.2 |

## 2. Chuẩn bị trên Google Cloud Console

Làm một lần cho cả project. Người có quyền Owner thực hiện.

1. **Chọn project** `ai-codguard` ở ô chọn project trên thanh trên cùng. Nếu trình duyệt đăng nhập nhiều tài khoản Google (URL có `authuser=1`), ghi nhớ tài khoản đang có quyền trên project và dùng đúng tài khoản đó khi đăng nhập `gcloud`.
2. **Billing**: vào Billing, kiểm tra project đã gắn billing account. Card "Billing" trên dashboard hiện "Estimated charges" nghĩa là đã gắn.
3. **Cảnh báo ngân sách** (nên làm): Billing → Budgets & alerts → Create budget, ví dụ 500.000 ₫, cảnh báo ở 50%, 90% và 100%.
4. **Bật API**: APIs and services → Library → tìm `aiplatform.googleapis.com` (tên hiển thị có thể là "Agent Platform API" hoặc "Vertex AI API") → Enable. Hoặc mở thẳng <https://console.cloud.google.com/apis/enableflow?apiid=aiplatform.googleapis.com>.
5. **Cấp quyền cho từng thành viên**: IAM and admin → IAM → Grant access → nhập email → role **Agent Platform User** (`roles/aiplatform.user`) → Save. Owner đã đủ quyền, không cần cấp thêm.

Popup "Configure Gemini Cloud Assist" là trợ lý AI của Console, không liên quan tới Gemini API mà backend gọi. Có thể đóng.

Bước 4 và 5 cũng làm được bằng `gcloud` sau khi cài ở mục 3:

```bash
gcloud services enable aiplatform.googleapis.com --project=ai-codguard
gcloud projects add-iam-policy-binding ai-codguard \
  --member="user:<email-thanh-vien>" --role="roles/aiplatform.user"
```

## 3. Cài đặt trên máy (macOS)

> Muốn thử ngay mà chưa cài gì: mở **Cloud Shell** (biểu tượng `>_` góc trên bên phải Console) rồi làm phần "Cách nhanh" ở bước 5.2. Cloud Shell có sẵn `gcloud` và đã đăng nhập.

```bash
# 1. Cài Google Cloud CLI (hoặc dùng bộ cài: https://cloud.google.com/sdk/docs/install)
brew install --cask gcloud-cli

# 2. Đăng nhập gcloud và chọn project
gcloud auth login
gcloud config set project ai-codguard

# 3. Tạo ADC cho code Python (trình duyệt mở ra, chọn cùng tài khoản ở bước 2)
gcloud auth application-default login
gcloud auth application-default set-quota-project ai-codguard

# 4. Kiểm tra: in ra một token dài là được
gcloud auth application-default print-access-token
```

ADC được lưu ở `~/.config/gcloud/application_default_credentials.json`, nằm ngoài repo. Không copy file này vào repo và không gửi cho người khác.

Tạo file `.env` ở thư mục gốc repo (`.gitignore` đã chặn file này):

```bash
cp .env.example .env
```

Sửa 2 dòng trong `.env`:

```bash
GOOGLE_CLOUD_PROJECT=ai-codguard
GEMINI_MODEL=<model-id>   # chọn ở mục 4
```

Python không tự đọc `.env`. Mọi lệnh ở mục 5 chạy từ `backend/` và nạp biến bằng `uv run --env-file ../.env`. Biến đặt trực tiếp trước lệnh được ưu tiên hơn giá trị trong `.env`, ví dụ `GEMINI_MODEL=gemini-3.5-flash uv run --env-file ../.env ...`.

```bash
cd backend
uv sync
```

## 4. Chọn model (`GEMINI_MODEL`)

Repo chưa chốt model ID. Thông tin từ trang model của Google ngày 12/10/2026:

| Model ID | Trạng thái | Pay-as-you-go (Standard PayGo) | `asia-southeast1` |
|---|---|---|---|
| [`gemini-3.8-flash`](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/gemini/3-8-flash) | GA từ 02/09/2026 | `global`, `us`, `eu` | Trang model không liệt kê |
| [`gemini-3.5-flash`](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/gemini/3-5-flash) | GA từ 19/05/2026 | `global`, `us`, `eu` | Có trong danh sách region, nhưng chỉ ghi cho Provisioned Throughput (mua trước công suất) |
| [`gemini-2.5-flash`](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/gemini/2-5-flash) | **Ngừng trên Agent Platform ngày 20/10/2026** | Không ghi theo region | Có, nhưng model sắp ngừng: không chọn |

Trang [Deployments and endpoints](https://docs.cloud.google.com/gemini-enterprise-agent-platform/resources/locations) lại liệt kê `gemini-3.8-flash` và `gemini-3.5-flash` ở `asia-southeast1` mà không ghi hình thức tính tiền. Tài liệu chưa thống nhất, vì vậy **kết quả smoke test ở bước 5.2 là căn cứ cuối cùng**:

1. Chạy smoke test ở `asia-southeast1` với từng model muốn dùng (mỗi lần 1 request).
2. Nếu lỗi `404 NOT_FOUND` kiểu "Publisher Model ... was not found or your project does not have access to it", chạy lại với `SMOKE_LOCATION=global`.
3. Nếu `global` chạy được mà `asia-southeast1` không, E3 sẽ không gọi được model đó. **Đừng tự sửa `TEXT_LOCATION`**, hãy báo team. Đổi region là thay đổi code và cũng là quyết định về dữ liệu: endpoint `global` không cam kết xử lý dữ liệu ở region nào. Với dữ liệu demo đã ẩn danh thì chấp nhận được (giống quyết định chạy Live API ở `us-central1`), nhưng phải ghi rõ trong PR.

## 5. Test từng bước

Chạy theo thứ tự, từ `backend/`. Bước sau tốn tiền hơn bước trước.

### 5.1 Unit test và offline eval (không cần credentials, không tốn tiền)

```bash
uv run pytest
uv run python -m scoring.ai.eval --offline --output /tmp/e3-offline.json
```

Kết quả mong đợi: tất cả test pass, eval in `status=checks_passed`. Ghi ra `/tmp` để không ghi đè báo cáo đã commit ở `docs/evaluations/e3-offline.json`.

### 5.2 Smoke test: 1 request, thấy lỗi thật

Bước này kiểm tra cùng lúc API, quyền, ADC, model và region. Khác với code E3, lỗi được in ra đầy đủ.

```bash
uv run --env-file ../.env python - <<'EOF'
import os

from google import genai

project = os.environ["GOOGLE_CLOUD_PROJECT"]
model = os.environ["GEMINI_MODEL"]
location = os.getenv("SMOKE_LOCATION", "asia-southeast1")  # E3 uses asia-southeast1

client = genai.Client(enterprise=True, project=project, location=location)
response = client.models.generate_content(model=model, contents="Trả lời đúng một từ: OK")
print(f"{location} / {model} -> {response.text!r}")
EOF
```

Thành công khi thấy dòng dạng `asia-southeast1 / <model> -> 'OK'`. Muốn thử region khác, thêm `SMOKE_LOCATION=global` trước `uv run`.

**Cách nhanh trong Cloud Shell** (không cần Python, không cần ADC):

```bash
PROJECT_ID=ai-codguard
MODEL=gemini-3.5-flash        # model muốn thử
LOCATION=asia-southeast1      # thử thêm: global
if [ "$LOCATION" = global ]; then HOST=aiplatform.googleapis.com; else HOST=$LOCATION-aiplatform.googleapis.com; fi
curl -s -X POST \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "Content-Type: application/json" \
  "https://$HOST/v1/projects/$PROJECT_ID/locations/$LOCATION/publishers/google/models/$MODEL:generateContent" \
  -d '{"contents":[{"role":"user","parts":[{"text":"Trả lời đúng một từ: OK"}]}]}'
```

Thành công khi JSON trả về có `"text": "OK"`. Nếu lỗi, tra bảng ở mục 8.

### 5.3 Một đơn qua code E3

Chạy đúng đường đi của E3 (prompt, schema, gateway) trên đơn tổng hợp `e3-001` của bộ eval. Tốn 1–2 request.

```bash
uv run --env-file ../.env python - <<'EOF'
import asyncio

from scoring.ai.address import extract_address
from scoring.ai.client import GeminiClient
from scoring.ai.eval import DEFAULT_INPUT, load_cases


async def main() -> None:
    case = load_cases(DEFAULT_INPUT)[0]  # synthetic order e3-001
    client = GeminiClient(cache_size=0)
    try:
        result = await extract_address(client, case.order.address)
    finally:
        await client.aclose()
    print("gateway events:", dict(client.stats))
    print("signals:", [(s.key, s.value) for s in result.signals] if result else None)


asyncio.run(main())
EOF
```

Đọc dòng `gateway events`:

| Event | Ý nghĩa | Việc cần làm |
|---|---|---|
| `success` | Gọi Gemini thành công, `signals` có giá trị | Xong |
| `unavailable` | Thiếu `GOOGLE_CLOUD_PROJECT` hoặc `GEMINI_MODEL` | Kiểm tra `.env` và tham số `--env-file` |
| `error` | SDK lỗi (auth, quyền, model, region), message bị giấu | Chạy lại bước 5.2 để xem lỗi |
| `timeout` | Quá `GEMINI_TIMEOUT_SECONDS` | Thêm `GEMINI_TIMEOUT_SECONDS=30` trước lệnh |
| `invalid_response`, `invalid_exhausted` | Model trả JSON sai schema (đã thử lại 1 lần) | Ghi lại model ID, báo người phụ trách prompt |
| `call_cap` | Hết `GEMINI_MAX_CALLS` | Tăng giới hạn |

### 5.4 Eval live trên 30 đơn

```bash
GEMINI_MAX_CALLS=150 uv run --env-file ../.env python -m scoring.ai.eval --output /tmp/e3-live.json
```

- Khoảng 60 request nếu không phải thử lại (bản offline dùng 61 response), có thể vượt 100 nếu model trả sai schema. `GEMINI_MAX_CALLS=150` để eval không bị cắt giữa chừng. Eval tắt cache, nên mỗi lần chạy lại đều tính tiền lại.
- Đọc `status` trong dòng kết quả:
  - `checks_passed`: các kiểm tra tự động đều đạt.
  - `check_failed`: có lý do không qua checker, hoặc trích dẫn tín hiệu không được phép.
  - `incomplete_live_run`: có lỗi gateway (xem `gateway_events` trong file báo cáo). Không dùng lần chạy này để nghiệm thu.
- Lần chạy để nghiệm thu E3.3 ("0 lý do bịa trên bộ 30 đơn mẫu"): ghi báo cáo ra `../docs/evaluations/e3-live.json`, sau đó **một thành viên khác đọc lại toàn bộ lý do cuối cùng** trong báo cáo. Kiểm tra tự động không chứng minh được là không có lý do bịa.

## 6. API key: khi nào dùng, cấu hình thế nào

### 6.1 Backend không dùng API key

Đặt `GOOGLE_API_KEY` hay `GEMINI_API_KEY` không có tác dụng với E3: code truyền `project` và `location`, nên SDK dùng ADC và bỏ qua key trong biến môi trường. Đây là chủ đích thiết kế ([gemini-live.md](gemini-live.md): "no API key to manage"): không có key để lộ, và chi phí tính vào credits của project.

Muốn backend chạy bằng API key thì phải sửa `client.py`. Đó là thay đổi kiến trúc: nêu trong PR, đừng tự thêm.

### 6.2 API key Google AI Studio (thử nhanh cá nhân)

Chỉ dùng để thử prompt với **dữ liệu tổng hợp**. Cách này không thay thế cấu hình ở mục 2–3.

1. Vào <https://aistudio.google.com/apikey> → Create API key → chọn project Google Cloud.
2. Nạp key vào terminal hiện tại, không ghi vào file nào trong repo:

   ```bash
   read -s GEMINI_API_KEY && export GEMINI_API_KEY   # dán key rồi nhấn Enter
   ```

3. Gửi thử:

   ```bash
   curl -s "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash:generateContent" \
     -H "x-goog-api-key: $GEMINI_API_KEY" \
     -H "Content-Type: application/json" \
     -X POST -d '{"contents":[{"parts":[{"text":"Trả lời đúng một từ: OK"}]}]}'
   ```

   Key sai sẽ trả `400` với `API_KEY_INVALID`. Trong Python, dùng `genai.Client(api_key=os.environ["GEMINI_API_KEY"])`, không có `enterprise=True`.

Lưu ý:

- Đây là Gemini Developer API (`generativelanguage.googleapis.com`), hệ thống khác với Agent Platform: quota, danh sách model và chính sách dữ liệu đều khác. Prompt chạy tốt ở đây chưa chắc cho kết quả giống trong E3.
- Ở gói miễn phí, Google có thể dùng nội dung gửi lên để cải thiện sản phẩm ([điều khoản Gemini API](https://ai.google.dev/gemini-api/terms)). Chỉ gửi dữ liệu tổng hợp, không bao giờ gửi dữ liệu người mua thật.
- Không commit key, không đưa key vào frontend, không dán vào issue, PR hay chat. Xóa key sau cuộc thi. Nếu lộ key, xóa ngay trong AI Studio.

### 6.3 API key của Agent Platform

Console cũng tạo được API key cho Agent Platform (trang Getting started: <https://console.cloud.google.com/agent-platform/overview>). Key thường vẫn cần role `roles/aiplatform.user`; key "express mode" thì không. Team không cần loại key này; nếu muốn dùng, đọc [Get an API key](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/start/api-keys).

## 7. Trên Cloud Run

Service `codguard-api` chạy bằng service account `codguard-runtime@ai-codguard.iam.gserviceaccount.com`. Không cần file key hay API key, nhưng cần 2 điều sau trước khi E2 nối E3 vào luồng chấm điểm:

1. Service account có role `roles/aiplatform.user`. Kiểm tra và cấp quyền:

   ```bash
   gcloud projects get-iam-policy ai-codguard \
     --flatten="bindings[].members" \
     --filter="bindings.members:codguard-runtime@ai-codguard.iam.gserviceaccount.com" \
     --format="value(bindings.role)"

   gcloud projects add-iam-policy-binding ai-codguard \
     --member="serviceAccount:codguard-runtime@ai-codguard.iam.gserviceaccount.com" \
     --role="roles/aiplatform.user"
   ```

2. Service có biến `GOOGLE_CLOUD_PROJECT` và `GEMINI_MODEL`. Cloud Run không tự đặt `GOOGLE_CLOUD_PROJECT`, và bước deploy trong `.github/workflows/ci.yml` hiện chưa đặt 2 biến này. Thiếu biến thì E3 âm thầm trả về tín hiệu rỗng (event `unavailable`). Thêm vào cấu hình deploy (E1.2) qua PR, không sửa tay trên Console.

## 8. Lỗi thường gặp

| Lỗi (thấy ở bước 5.2) | Nguyên nhân | Cách sửa |
|---|---|---|
| `DefaultCredentialsError: Your default credentials were not found` | Chưa tạo ADC | `gcloud auth application-default login` |
| `403 PERMISSION_DENIED`, có `SERVICE_DISABLED` hoặc "API has not been used in project" | Chưa bật API | Bật `aiplatform.googleapis.com` (mục 2), đợi vài phút rồi thử lại |
| `403 PERMISSION_DENIED`, có `aiplatform.endpoints.predict` | Tài khoản thiếu quyền | Cấp `roles/aiplatform.user` (mục 2) |
| `404 NOT_FOUND`, có "Publisher Model" | Sai model ID, hoặc model không có ở region đó | Kiểm tra ID, thử `SMOKE_LOCATION=global` (mục 4) |
| `429 RESOURCE_EXHAUSTED` | Hết quota theo phút | Đợi một lúc rồi chạy lại; xem IAM and admin → Quotas |
| Cảnh báo "without a quota project" | ADC chưa gắn quota project | `gcloud auth application-default set-quota-project ai-codguard` |
| `KeyError: 'GOOGLE_CLOUD_PROJECT'`, hoặc eval báo `Live evaluation requires GEMINI_MODEL` | Chưa nạp `.env` | Thêm `--env-file ../.env` và chạy từ `backend/` |
| Vẫn `403` dù đã cấp quyền | ADC đăng nhập bằng tài khoản khác | `gcloud auth list` để xem tài khoản, rồi chạy lại `gcloud auth application-default login` với đúng tài khoản |

## 9. Bảo mật

- Không commit `.env`, API key, file ADC hay file key của service account. `.gitignore` đã chặn `.env`, nhưng vẫn xem `git status` trước khi commit.
- Chỉ test bằng dữ liệu tổng hợp. Bộ eval `backend/tests/data/e3_eval_orders.jsonl` là đủ; không dán đơn hàng thật vào prompt.
- Dùng máy chung thì xóa ADC khi xong: `gcloud auth application-default revoke`.
- Đường demo công khai phải giới hạn số lần gọi Gemini (E1.4) để không bị dùng hết quota.
