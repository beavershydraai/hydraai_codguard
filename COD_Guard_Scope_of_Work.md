# COD Guard — Scope of Work (Hackathon Prototype)

| | |
|---|---|
| **Sản phẩm** | COD Guard: chấm điểm rủi ro bom hàng cho đơn COD của shop bán qua social và website, giải thích lý do, và tự động chọn hành động phù hợp (gửi ngay, nhắn xác nhận, AI gọi điện, yêu cầu cọc, giữ lại chờ duyệt) |
| **Mục tiêu** | Prototype chạy end-to-end, deploy trên Google Cloud, nộp AI Builder Cup trước **18/10/2026** |
| **Thời gian** | 7/10 → 18/10 (12 ngày lịch) |
| **Đơn vị ước lượng** | Ngày công (1 người làm toàn thời gian 1 ngày) |
| **Ưu tiên** | **Must** = bắt buộc cho demo · **Should** = nên có, cắt được nếu thiếu người · **Could** = làm thêm nếu dư thời gian |

---

## 1. Deliverables nộp bài

| # | Deliverable | Done khi |
|---|---|---|
| D1 | Prototype web app chạy thật trên Cloud Run / Firebase | Giám khảo mở link, đi hết luồng: đơn vào → chấm điểm + lý do → hành động → cuộc gọi AI → kết quả → dashboard |
| D2 | Video demo 3 phút | Có clip cuộc gọi tiếng Anh, clip cuộc gọi tiếng Việt và các con số bằng chứng |
| D3 | Pitch deck / proposal | Nêu đủ vấn đề, giải pháp, bằng chứng, đối thủ, lộ trình |
| D4 | GitHub repo + README + sơ đồ kiến trúc | Người ngoài clone về là chạy được theo README |
| D5 | Báo cáo backtest | Lift chart, so sánh với 2 baseline, ước tính tiền tiết kiệm |
| D6 | Báo cáo test 50 cuộc gọi | Tỷ lệ cuộc gọi xử lý đúng theo từng kịch bản |

---

## 2. Workstreams và hạng mục công việc

### WS0 — Setup & điều kiện dự thi

| ID | Hạng mục | Done khi | Ưu tiên | Ngày công |
|---|---|---|---|---|
| 0.1 | Xác nhận điều kiện dự thi (Việt Nam, người đi làm) và đăng ký đội | Đã đăng ký trước 11/10 | Must | 0,1 |
| 0.2 | GCP project, billing/credit, region `asia-southeast1`, Secret Manager | Cả team truy cập được | Must | 0,25 |
| 0.3 | Repo, nhánh làm việc, deploy tự động lên Cloud Run + Firebase Hosting | Mỗi lần merge là có bản chạy trên cloud | Must | 0,5 |
| 0.4 | Môi trường demo có seed data cố định, reset được | Chạy lại demo ra kết quả giống nhau | Must | 0,25 |

### WS1 — Data & mô hình chấm điểm

| ID | Hạng mục | Done khi | Ưu tiên | Ngày công |
|---|---|---|---|---|
| 1.1 | Chốt nguồn data (data shop thật hoặc bộ dữ liệu TMĐT công khai có đơn COD); kiểm tra cột COD, trạng thái, mã khách | Có quyết định trước 9/10 | Must | 0,5 |
| 1.2 | Làm sạch data, chuẩn hóa schema đơn hàng | Một bảng đơn thống nhất. Nhãn "thất bại" chỉ tính lỗi do người mua (từ chối nhận, không liên lạc được), không tính lỗi của hãng vận chuyển hay shop | Must | 1 |
| 1.3 | Bộ sinh data giả lập cho bối cảnh Việt Nam (địa chỉ, livestream, đơn quà, spam), có cài sẵn các mẫu bom hàng | Đủ cho UI demo và các ca test | Must | 1 |
| 1.4 | Tính tín hiệu cho mỗi đơn | Mỗi đơn có đủ các nhóm: lịch sử SĐT, chất lượng địa chỉ, hành vi đặt hàng, tần suất bất thường, ngữ cảnh, số tiền thu hộ | Must | 1 |
| 1.5 | Train model, lấy giải thích theo từng tín hiệu | Ra xác suất + top tín hiệu cho mỗi đơn | Must | 1 |
| 1.6 | Hard rules + tính expected loss + chia tier | Pass cả 4 điều kiện:<br>• Đơn trả trước được bỏ qua<br>• Expected loss tính theo số tiền còn phải thu<br>• SĐT có tỷ lệ hoàn ≥75% (tối thiểu 3 đơn) xếp Very High<br>• Vị trí địa lý không bao giờ là lý do duy nhất cho High/Very High | Must | 0,5 |
| 1.7 | Backtest so với 2 baseline ("chỉ dùng lịch sử SĐT", "gọi tất cả") + lift chart | Ra D5 | Must | 1 |

### WS2 — Tín hiệu AI & lý do (Gemini)

| ID | Hạng mục | Done khi | Ưu tiên | Ngày công |
|---|---|---|---|---|
| 2.1 | Chấm mức đầy đủ của địa chỉ, phát hiện địa chỉ mơ hồ, xử lý tên địa giới cũ/mới sau sáp nhập 2025 | Trả về điểm và cờ có cấu trúc | Must | 0,5 |
| 2.2 | Rút tín hiệu từ đoạn hội thoại chốt đơn | Trả về các cờ: có hỏi kỹ / chốt vội / lệch tên | Should | 0,5 |
| 2.3 | Viết tối đa 3 lý do bằng tiếng Việt, có bước kiểm tra lý do khớp tín hiệu thật. AI chỉ viết lý do, không quyết định điểm | 0 lý do bịa trên bộ 30 đơn mẫu | Must | 0,5 |
| 2.4 | Bộ đơn mẫu để đánh giá chất lượng prompt | 30 đơn có đáp án mong đợi | Should | 0,5 |

### WS3 — Quyết định & điều phối

| ID | Hạng mục | Done khi | Ưu tiên | Ngày công |
|---|---|---|---|---|
| 3.1 | Vòng đời đơn hàng | Có đủ các trạng thái: Mới, Được gửi, Chờ xác nhận, Chờ cọc, Chờ duyệt, Đã hủy, Đã gửi, Giao thành công, Giao thất bại.<br>Sửa đơn trước khi gửi thì chấm lại. Đơn đã xác nhận không bị liên hệ lại | Must | 1 |
| 3.2 | Policy engine: policy mặc định, chọn hành động theo tier, leo thang khi không phản hồi | Theo đúng policy mặc định:<br>• Low → gửi ngay<br>• Medium → link xác nhận, gọi AI nếu 2 giờ không phản hồi<br>• High → gọi AI<br>• Very High → yêu cầu cọc<br>Không liên hệ khi expected loss thấp hơn chi phí liên hệ | Must | 1 |
| 3.3 | Bảo vệ liên hệ: tối đa 1 cuộc gọi/SĐT/ngày, gộp đơn trong 15 phút, chỉ liên hệ 8h–21h, chặn 30 ngày khi bị báo "không đặt", tin tưởng 7 ngày sau khi xác nhận | Pass kịch bản spam: 50 đơn → 1 lần liên hệ → chặn | Must | 1 |
| 3.4 | Xử lý đơn quà tặng | Chỉ xác minh với người đặt, không bao giờ liên hệ người nhận | Must | 0,25 |
| 3.5 | Logic hàng chờ duyệt tay + override có ghi lý do | Mọi override vào audit log | Must | 0,5 |
| 3.6 | Điều phối các bước bằng ADK (chấm điểm → quyết định → liên hệ) | Một đơn mới chạy hết pipeline tự động | Should | 0,5 |

### WS4 — Cuộc gọi AI (Gemini Live)

| ID | Hạng mục | Done khi | Ưu tiên | Ngày công |
|---|---|---|---|---|
| 4.1 | **Spike ngày 1:** test chất lượng tiếng Việt + độ trễ của Gemini Live | Quyết định go/no-go trước 9/10 | Must | 0,5 |
| 4.2 | "Điện thoại giả lập" trên trình duyệt, stream audio hai chiều | Nói chuyện được ngay trong web app | Must | 1 |
| 4.3 | Thiết kế hội thoại: tự giới thiệu là AI + tên shop, đọc tóm tắt đơn, xử lý xác nhận / sửa / hủy / "không đặt" / nhầm người / xin gặp người thật, đọc lại thay đổi, chỉ nói nội dung đơn hàng | Mỗi cuộc gọi ghi đúng 1 trong 7 kết quả: Xác nhận, Đã sửa, Hủy, Không đặt, Không nghe máy, Nhầm người, Không rõ | Must | 1,5 |
| 4.4 | Ghi outcome, tóm tắt cuộc gọi, kích hoạt chấm lại khi có thay đổi | Outcome và tóm tắt hiện trên trang đơn | Must | 0,5 |
| 4.5 | Bộ test 50 cuộc gọi (kịch bản, giọng vùng miền, môi trường ồn) | Ra D6, mục tiêu ≥45/50 | Must | 1 |
| 4.6 | Gọi số thật qua tổng đài (Twilio/Stringee) tới số đã xác minh | Gọi được cho thành viên team | Could | 1,5 |

### WS5 — Trang xác nhận & tin nhắn

| ID | Hạng mục | Done khi | Ưu tiên | Ngày công |
|---|---|---|---|---|
| 5.1 | Trang xác nhận không cần đăng nhập: Xác nhận / Sửa địa chỉ / Hủy / "Tôi không đặt"; dữ liệu cá nhân che một phần; link hết hạn sau 48 giờ | Mỗi thao tác cập nhật đúng trạng thái đơn | Must | 1 |
| 5.2 | Preview giả lập tin Zalo ZNS / SMS | Hiện trong demo, có nhãn "mock" | Should | 0,25 |

### WS6 — Web app cho shop

| ID | Hạng mục | Done khi | Ưu tiên | Ngày công |
|---|---|---|---|---|
| 6.1 | Onboarding: tạo shop, chi phí giao thất bại, giờ liên hệ, policy mặc định | Có giá trị mặc định, shop dùng được ngay | Must | 1 |
| 6.2 | Hộp đơn hàng: import file, danh sách đơn theo trạng thái và tier | Import 1.000 đơn không lỗi | Must | 1 |
| 6.3 | Trang chi tiết đơn: điểm, lý do, lịch sử điểm, lịch sử liên hệ, tóm tắt cuộc gọi, override | Hiển thị đủ các thông tin trên; override được ghi lại | Must | 1 |
| 6.4 | Màn hàng chờ duyệt tay | Duyệt / yêu cầu cọc / hủy được | Must | 0,5 |
| 6.5 | Màn cài đặt policy theo tier | Đổi policy chỉ áp dụng cho quyết định sau thời điểm đổi | Should | 0,5 |
| 6.6 | Dashboard ROI + màn kết quả backtest; empty state khi chưa có dữ liệu | Hiển thị đủ: số đơn đã sàng lọc, hành động theo loại, đơn hủy trước khi gửi, đơn giao thất bại, tiền tiết kiệm ước tính, tỷ lệ đơn tốt bị làm phiền. Số liệu dự đoán có nhãn "ước tính" | Must | 1,5 |
| 6.7 | Phân quyền Shop Owner / Shop Staff | Staff không sửa được policy và chi phí | Should | 0,5 |
| 6.8 | Chau chuốt UI/UX (nhắm giải Best UI/UX) | Qua review nội bộ | Should | 1 |

### WS7 — Tích hợp

| ID | Hạng mục | Done khi | Ưu tiên | Ngày công |
|---|---|---|---|---|
| 7.1 | Kết nối nhận đơn tự động (để sales tool gửi đơn sang) | Gửi 1 đơn mẫu thì đơn được chấm điểm | Must | 0,5 |
| 7.2 | GHN môi trường test: tạo đơn test, nhận trạng thái giao | Có ít nhất 1 vòng đơn thật trên GHN staging | Should | 1 |
| 7.3 | Import kết quả giao + cập nhật lịch sử SĐT | Kết quả giao làm thay đổi lịch sử SĐT | Must | 0,5 |

### WS8 — Bảo mật & tuân thủ

| ID | Hạng mục | Done khi | Ưu tiên | Ngày công |
|---|---|---|---|---|
| 8.1 | Hash SĐT khi dùng chung giữa các shop; demo chỉ dùng data đã ẩn danh | Không có SĐT thật trong demo và video | Must | 0,5 |
| 8.2 | Audit log cho thay đổi policy và override | Xem lại được ai đổi gì, lúc nào | Should | 0,25 |
| 8.3 | Giới hạn số lần gọi Gemini khi giám khảo tự bấm thử | Không hết quota trong lúc chấm | Must | 0,25 |

### WS9 — Bằng chứng hiệu quả

| ID | Hạng mục | Done khi | Ưu tiên | Ngày công |
|---|---|---|---|---|
| 9.1 | Mô phỏng chi phí 4 chính sách (không làm gì / gọi tất cả / cọc tất cả / COD Guard), dùng phí GHN/GHTK thật | Ra số tiền tiết kiệm/tháng cho shop 300 đơn/ngày | Must | 0,5 |
| 9.2 | Script mô phỏng tấn công spam (50 đơn, 20 tài khoản, 1 SĐT) | Chạy được ngay trong demo | Must | 0,25 |
| 9.3 | Slide bối cảnh cạnh tranh + số liệu từ Ấn Độ (ghi rõ do vendor công bố) | Có trong deck | Should | 0,25 |

### WS10 — Nộp bài

| ID | Hạng mục | Done khi | Ưu tiên | Ngày công |
|---|---|---|---|---|
| 10.1 | Kịch bản demo 3 phút | Team duyệt | Must | 0,5 |
| 10.2 | Quay và dựng video (cuộc gọi tiếng Anh + tiếng Việt) | Ra D2 | Must | 1,5 |
| 10.3 | Pitch deck / proposal | Ra D3 | Must | 1,5 |
| 10.4 | README + sơ đồ kiến trúc | Ra D4 | Must | 0,5 |
| 10.5 | Chạy thử toàn bộ và nộp bài | Nộp trước hạn, đã kiểm tra lại link | Must | 0,5 |

---

## 3. Tổng khối lượng

| Workstream | Must | Should | Could |
|---|---|---|---|
| WS0 Setup | 1,1 | — | — |
| WS1 Data & mô hình | 6 | — | — |
| WS2 Tín hiệu AI | 1 | 1 | — |
| WS3 Quyết định | 3,75 | 0,5 | — |
| WS4 Cuộc gọi AI | 4,5 | — | 1,5 |
| WS5 Trang xác nhận | 1 | 0,25 | — |
| WS6 Web app | 5 | 2 | — |
| WS7 Tích hợp | 1 | 1 | — |
| WS8 Bảo mật | 0,75 | 0,25 | — |
| WS9 Bằng chứng | 0,75 | 0,25 | — |
| WS10 Nộp bài | 4,5 | — | — |
| **Tổng** | **~29,4** | **~5,25** | **1,5** |

**Đường cắt scope:**

- Đội 4 người làm toàn thời gian khoảng 10 ngày có ~40 ngày công: làm đủ Must + Should.
- Thành viên chỉ làm buổi tối và cuối tuần, hoặc đội 3 người: chỉ làm Must (~29 ngày công) và bỏ toàn bộ Should.
- Hạng mục Could (gọi số thật) chuyển sang sau hạn nộp, làm trước vòng chung kết 4/12.

---

## 4. Mốc thời gian

| Mốc | Ngày | Cần đạt |
|---|---|---|
| **M1 — Gỡ rủi ro** | 9/10 | Đã chốt nguồn data (1.1). Có kết quả spike Gemini Live tiếng Việt (4.1). Deploy tự động chạy được (0.3).<br>Chốt 3 quyết định: bản nộp có gọi số thật hay không; nguồn data; COD Guard chỉ gợi ý hay tự đẩy đơn sang hãng vận chuyển |
| Đăng ký | 11/10 | Đã đăng ký đội, đã xác nhận điều kiện dự thi (0.1) |
| **M2 — Chạy end-to-end** | 13/10 | Đơn vào → chấm điểm + lý do → quyết định → cuộc gọi trên trình duyệt → outcome. Giao diện còn thô cũng được |
| **M3 — Feature freeze** | 16/10 (tối) | Dashboard, backtest, trang xác nhận, bộ test 50 cuộc gọi đều xong. Sau mốc này chỉ sửa lỗi |
| **M4 — Nộp bài** | 18/10 | Video, deck, README; đã chạy thử toàn bộ và nộp (kiểm tra giờ và múi giờ chính xác của hạn nộp) |

---

## 5. Phân công gợi ý (4 người)

| Vai trò | Workstream | Ngày công (Must + Should) |
|---|---|---|
| P1 — Data/ML | WS1, WS2, WS9 | ~9 |
| P2 — Voice | WS4, WS5; hỗ trợ quay video | ~5,75 |
| P3 — Backend | WS0, WS3, WS7, WS8 | ~8,35 |
| P4 — Frontend/Product | WS6, WS10 | ~11,5 (nặng nhất, nên P2 và P1 hỗ trợ video và deck) |

Nếu đội chỉ có 3 người: gộp P2 và P3, đồng thời bỏ các hạng mục Should.

---

## 6. Rủi ro chính

| Rủi ro | Cách xử lý |
|---|---|
| Gemini Live xử lý tiếng Việt chưa đạt | Spike ngay ngày 1 (4.1). Nếu chưa đạt: demo cuộc gọi tiếng Anh, còn tiếng Việt đi qua trang xác nhận |
| Không có data thật | Dùng bộ dữ liệu công khai cho backtest, data giả lập cho UI, và nói rõ điều này khi pitch |
| Thành viên chỉ làm bán thời gian | Áp dụng đường cắt scope ở mục 3 ngay từ M1 |
| Scope phình ra | Feature freeze tối 16/10; mọi ý tưởng mới ghi vào lộ trình |
| Lỗi deploy sát giờ nộp | Deploy hằng ngày từ 8/10; khóa phiên bản demo từ ngày 17/10 |

---

## 7. Ngoài phạm vi

- Liên hệ người mua của đơn trên sàn (Shopee, Lazada, TikTok Shop)
- Gửi Zalo ZNS / SMS thật; gọi từ số tổng đài đã đăng ký
- Connector có sẵn cho Pancake, Haravan, Sapo, KiotViet
- Thanh toán cọc thật; xử lý thanh toán
- Lịch sử SĐT dùng chung giữa các shop ở môi trường thật
- Ứng dụng di động; tính phí shop; ngôn ngữ ngoài tiếng Việt và tiếng Anh
