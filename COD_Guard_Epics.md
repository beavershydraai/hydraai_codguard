# COD Guard — Epics & Sub-epics

**Quy ước:**

- **Cấu trúc issue:** Epic (issue cha) → Sub-epic (sub-issue). Task chi tiết sẽ tạo sau, làm sub-issue của sub-epic.
- **Ưu tiên:** Must · Should · Could
- **Estimate:** tính bằng ngày công
- **Milestone:** M1 = 9/10 · M2 = 13/10 · M3 = 16/10 · M4 = 18/10
- **Area** (dùng làm label): `area:platform` · `area:data` · `area:ai` · `area:backend` · `area:voice` · `area:frontend` · `area:integration` · `area:evidence` · `area:submission`

## Tổng quan

| Epic | Tên | Area | Must | Should | Could |
|---|---|---|---|---|---|
| E1 | Nền tảng, DevOps & bảo mật | platform | 1,75 | — | — |
| E2 | Data & mô hình rủi ro | data | 5 | — | — |
| E3 | Tín hiệu AI & lý do (Gemini) | ai | 1 | 1 | — |
| E4 | Decision engine | backend | 3,75 | 0,75 | — |
| E5 | Cuộc gọi AI xác nhận đơn | voice | 3,5 | — | 1,5 |
| E6 | Trang xác nhận cho người mua | voice | 1 | 0,25 | — |
| E7 | Web app cho shop | frontend | 5 | 2 | — |
| E8 | Tích hợp | integration | 1 | 1 | — |
| E9 | Bằng chứng & kiểm chứng | evidence | 2,75 | 0,25 | — |
| E10 | Nộp bài | submission | 4,6 | — | — |
| | **Tổng** | | **29,35** | **5,25** | **1,5** |

---

## E1 — Nền tảng, DevOps & bảo mật

**Mục tiêu:** cả team deploy được lên Google Cloud từ ngày đầu; dữ liệu cá nhân được bảo vệ; demo ổn định khi giám khảo dùng thử.

| ID | Sub-epic | Done khi | Ưu tiên | Est. | Milestone | Phụ thuộc |
|---|---|---|---|---|---|---|
| E1.1 | Tạo GCP project, billing, region `asia-southeast1`, Secret Manager | Cả team truy cập được; không có secret trong code | Must | 0,25 | M1 | — |
| E1.2 | Pipeline deploy tự động lên Cloud Run + Firebase Hosting | Mỗi lần merge là có bản chạy trên cloud | Must | 0,5 | M1 | E1.1 |
| E1.3 | Môi trường demo có seed data cố định, reset được | Chạy lại demo ra kết quả giống nhau | Must | 0,25 | M3 | E2.2 |
| E1.4 | Giới hạn số lần gọi Gemini khi giám khảo dùng thử | Không hết quota trong lúc chấm | Must | 0,25 | M3 | E1.2 |
| E1.5 | Hash SĐT khi dùng chung giữa các shop; ẩn danh toàn bộ data demo | Không có SĐT thật trong demo và video | Must | 0,5 | M3 | E2.1 |

## E2 — Data & mô hình rủi ro

**Mục tiêu:** mỗi đơn COD có xác suất bom hàng, tier và expected loss, tính trên dữ liệu sạch.

| ID | Sub-epic | Done khi | Ưu tiên | Est. | Milestone | Phụ thuộc |
|---|---|---|---|---|---|---|
| E2.1 | Chốt nguồn data, làm sạch, chuẩn hóa schema đơn hàng | Có một bảng đơn thống nhất. Nhãn "thất bại" chỉ tính lỗi do người mua (từ chối nhận, không liên lạc được) | Must | 1,5 | M1 | — |
| E2.2 | Bộ sinh data giả lập bối cảnh Việt Nam (địa chỉ, livestream, đơn quà, spam), có cài sẵn các mẫu bom hàng | Đủ data cho UI demo và các ca test | Must | 1 | M2 | — |
| E2.3 | Tính tín hiệu rủi ro cho mỗi đơn | Mỗi đơn có đủ các nhóm: lịch sử SĐT, chất lượng địa chỉ, hành vi đặt hàng, tần suất bất thường, ngữ cảnh, số tiền thu hộ | Must | 1 | M2 | E2.1, E2.2 |
| E2.4 | Train mô hình rủi ro, lấy giải thích theo từng tín hiệu | Ra xác suất + các tín hiệu đóng góp nhiều nhất cho mỗi đơn | Must | 1 | M2 | E2.3, E3.1 |
| E2.5 | Hard rules, expected loss, chia tier | Thỏa cả 4 điều kiện:<br>• Đơn trả trước được bỏ qua<br>• Expected loss tính theo số tiền còn phải thu<br>• SĐT có tỷ lệ hoàn ≥75% (tối thiểu 3 đơn) xếp Very High<br>• Vị trí địa lý không bao giờ là lý do duy nhất cho High/Very High | Must | 0,5 | M2 | E2.4 |

## E3 — Tín hiệu AI & lý do (Gemini)

**Mục tiêu:** Gemini rút tín hiệu từ dữ liệu dạng chữ và viết lý do dễ hiểu. Gemini không tự quyết định điểm.

| ID | Sub-epic | Done khi | Ưu tiên | Est. | Milestone | Phụ thuộc |
|---|---|---|---|---|---|---|
| E3.1 | Chấm mức đầy đủ của địa chỉ, phát hiện địa chỉ mơ hồ, xử lý tên địa giới cũ/mới sau sáp nhập 2025 | Trả về điểm và cờ có cấu trúc | Must | 0,5 | M2 | E1.1 |
| E3.2 | Rút tín hiệu từ đoạn hội thoại chốt đơn | Trả về các cờ: có hỏi kỹ / chốt vội / lệch tên | Should | 0,5 | M3 | E1.1 |
| E3.3 | Viết tối đa 3 lý do bằng tiếng Việt, kèm bước kiểm tra lý do khớp tín hiệu thật | 0 lý do bịa trên bộ 30 đơn mẫu | Must | 0,5 | M2 | E2.4 |
| E3.4 | Bộ 30 đơn mẫu có đáp án để đánh giá prompt | Dùng được cho E3.1 và E3.3 | Should | 0,5 | M2 | — |

## E4 — Decision engine

**Mục tiêu:** mỗi đơn đi đúng vòng đời, nhận đúng hành động, và người nhận được bảo vệ khỏi bị làm phiền.

| ID | Sub-epic | Done khi | Ưu tiên | Est. | Milestone | Phụ thuộc |
|---|---|---|---|---|---|---|
| E4.1 | Vòng đời đơn hàng | Có đủ các trạng thái: Mới, Được gửi, Chờ xác nhận, Chờ cọc, Chờ duyệt, Đã hủy, Đã gửi, Giao thành công, Giao thất bại.<br>Sửa đơn trước khi gửi thì chấm lại. Đơn đã xác nhận không bị liên hệ lại | Must | 1 | M2 | E1.1 |
| E4.2 | Policy engine: policy mặc định, chọn hành động theo tier, leo thang khi không phản hồi | Theo policy mặc định:<br>• Low → gửi ngay<br>• Medium → link xác nhận, gọi AI nếu 2 giờ không phản hồi<br>• High → gọi AI<br>• Very High → yêu cầu cọc<br>Không liên hệ khi expected loss thấp hơn chi phí liên hệ | Must | 1 | M2 | E4.1, E2.5 |
| E4.3 | Bảo vệ liên hệ & chống spam | Đủ các quy tắc:<br>• Tối đa 1 cuộc gọi/SĐT/ngày<br>• Gộp các đơn trong cùng 15 phút<br>• Chỉ liên hệ 8h–21h<br>• Chặn 30 ngày khi bị báo "không đặt"<br>• Tin tưởng 7 ngày sau khi xác nhận<br>Kịch bản test: 50 đơn spam chỉ tạo đúng 1 lần liên hệ, sau đó chặn | Must | 1 | M2 | E4.1 |
| E4.4 | Xử lý đơn quà tặng | Chỉ xác minh với người đặt, không bao giờ liên hệ người nhận | Must | 0,25 | M2 | E4.2 |
| E4.5 | Hàng chờ duyệt tay + override có ghi lý do | Override ghi lại người, thời điểm, lý do | Must | 0,5 | M2 | E4.1 |
| E4.6 | Audit log cho thay đổi policy và override | Xem lại được ai đổi gì, lúc nào | Should | 0,25 | M3 | E4.5 |
| E4.7 | Điều phối pipeline bằng ADK (chấm điểm → quyết định → liên hệ) | Một đơn mới chạy hết pipeline tự động | Should | 0,5 | M3 | E4.2, E5.4 |

## E5 — Cuộc gọi AI xác nhận đơn

**Mục tiêu:** AI gọi xác nhận đơn bằng tiếng Việt tự nhiên và ghi lại kết quả rõ ràng.

| ID | Sub-epic | Done khi | Ưu tiên | Est. | Milestone | Phụ thuộc |
|---|---|---|---|---|---|---|
| E5.1 | Spike Gemini Live: chất lượng tiếng Việt, giọng các miền, độ trễ | Có quyết định go/no-go | Must | 0,5 | M1 | E1.1 |
| E5.2 | Điện thoại giả lập trên trình duyệt, stream audio hai chiều | Nói chuyện được ngay trong web app | Must | 1 | M2 | E5.1 |
| E5.3 | Thiết kế hội thoại xác nhận đơn | Đủ các yêu cầu sau:<br>• Tự giới thiệu là AI + tên shop<br>• Đọc tóm tắt đơn<br>• Xử lý: xác nhận / sửa / hủy / "không đặt" / nhầm người / xin gặp người thật<br>• Đọc lại thay đổi trước khi kết thúc<br>• Chỉ nói nội dung đơn hàng | Must | 1,5 | M2 | E5.1 |
| E5.4 | Ghi kết quả cuộc gọi, tóm tắt, kích hoạt chấm lại khi có thay đổi | Mỗi cuộc gọi ghi đúng 1 trong 7 kết quả: Xác nhận, Đã sửa, Hủy, Không đặt, Không nghe máy, Nhầm người, Không rõ. Kết quả và tóm tắt hiện trên trang đơn | Must | 0,5 | M2 | E5.2, E5.3, E4.1 |
| E5.5 | Gọi số thật qua tổng đài (Twilio/Stringee) tới số đã xác minh | Gọi được cho thành viên team | Could | 1,5 | Sau M4 | E5.4 |

## E6 — Trang xác nhận cho người mua

**Mục tiêu:** người mua tự xác nhận hoặc sửa đơn không cần đăng nhập, và có thể báo đơn giả mạo.

| ID | Sub-epic | Done khi | Ưu tiên | Est. | Milestone | Phụ thuộc |
|---|---|---|---|---|---|---|
| E6.1 | Trang xác nhận: Xác nhận / Sửa địa chỉ / Hủy / "Tôi không đặt"; dữ liệu cá nhân che một phần; link hết hạn sau 48 giờ | Mỗi thao tác cập nhật đúng trạng thái đơn | Must | 1 | M3 | E4.1 |
| E6.2 | Preview giả lập tin Zalo ZNS / SMS | Hiện trong demo, có nhãn "mock" | Should | 0,25 | M3 | E6.1 |

## E7 — Web app cho shop

**Mục tiêu:** chủ shop và nhân viên xem được rủi ro, xử lý đơn, và thấy rõ hiệu quả.

| ID | Sub-epic | Done khi | Ưu tiên | Est. | Milestone | Phụ thuộc |
|---|---|---|---|---|---|---|
| E7.1 | Onboarding: tạo shop, chi phí giao thất bại, giờ liên hệ, policy mặc định | Có giá trị mặc định, shop dùng được ngay | Must | 1 | M2 | E1.2 |
| E7.2 | Hộp đơn hàng: import file, danh sách đơn theo trạng thái và tier | Import 1.000 đơn không lỗi | Must | 1 | M2 | E4.1 |
| E7.3 | Trang chi tiết đơn: điểm, lý do, lịch sử điểm, lịch sử liên hệ, tóm tắt cuộc gọi, override | Hiển thị đủ các thông tin trên; override được ghi lại | Must | 1 | M2 | E3.3, E5.4 |
| E7.4 | Màn hàng chờ duyệt tay | Duyệt / yêu cầu cọc / hủy được | Must | 0,5 | M3 | E4.5 |
| E7.5 | Dashboard ROI + màn kết quả backtest; empty state khi chưa có dữ liệu | Hiển thị đủ: số đơn đã sàng lọc, hành động theo loại, đơn hủy trước khi gửi, đơn giao thất bại, tiền tiết kiệm ước tính, tỷ lệ đơn tốt bị làm phiền. Số liệu dự đoán có nhãn "ước tính" | Must | 1,5 | M3 | E9.1, E8.3 |
| E7.6 | Màn cài đặt policy theo tier | Đổi policy chỉ áp dụng cho quyết định sau thời điểm đổi | Should | 0,5 | M3 | E4.2 |
| E7.7 | Phân quyền Shop Owner / Shop Staff | Staff không sửa được policy và chi phí | Should | 0,5 | M3 | E7.1 |
| E7.8 | Chau chuốt UI/UX (nhắm giải Best UI/UX) | Qua review nội bộ | Should | 1 | M3 | E7.5 |

## E8 — Tích hợp

**Mục tiêu:** nhận đơn tự động từ hệ thống bên ngoài, và nhận lại kết quả giao hàng để hệ thống tự học.

| ID | Sub-epic | Done khi | Ưu tiên | Est. | Milestone | Phụ thuộc |
|---|---|---|---|---|---|---|
| E8.1 | Kết nối nhận đơn tự động cho sales tool bên ngoài | Gửi 1 đơn mẫu thì đơn được chấm điểm | Must | 0,5 | M2 | E4.1 |
| E8.2 | GHN môi trường test: tạo đơn test, nhận trạng thái giao | Có ít nhất 1 vòng đơn thật trên GHN staging | Should | 1 | M3 | E1.1 |
| E8.3 | Import kết quả giao + cập nhật lịch sử SĐT | Kết quả giao làm thay đổi lịch sử SĐT | Must | 0,5 | M3 | E4.1 |

## E9 — Bằng chứng & kiểm chứng

**Mục tiêu:** có số liệu chứng minh COD Guard hiệu quả để đưa vào demo và pitch.

| ID | Sub-epic | Done khi | Ưu tiên | Est. | Milestone | Phụ thuộc |
|---|---|---|---|---|---|---|
| E9.1 | Backtest so với "chỉ dùng lịch sử SĐT" và "gọi tất cả"; vẽ lift chart | Có báo cáo backtest, kèm ước tính tiền tiết kiệm | Must | 1 | M3 | E2.5 |
| E9.2 | Chạy 50 cuộc gọi test (kịch bản, giọng các miền, môi trường ồn) | Có báo cáo, đạt ≥45/50 cuộc xử lý đúng | Must | 1 | M3 | E5.4 |
| E9.3 | Mô phỏng chi phí 4 chính sách (không làm gì / gọi tất cả / cọc tất cả / COD Guard), dùng phí GHN/GHTK thật | Ra số tiền tiết kiệm/tháng cho shop 300 đơn/ngày | Must | 0,5 | M3 | E9.1 |
| E9.4 | Script mô phỏng tấn công spam (50 đơn, 20 tài khoản, 1 SĐT) | Chạy được ngay trong demo | Must | 0,25 | M3 | E4.3 |
| E9.5 | Slide bối cảnh cạnh tranh + số liệu từ Ấn Độ (ghi rõ do vendor công bố) | Có trong deck | Should | 0,25 | M3 | — |

## E10 — Nộp bài

**Mục tiêu:** nộp đủ và đúng hạn trước 18/10.

| ID | Sub-epic | Done khi | Ưu tiên | Est. | Milestone | Phụ thuộc |
|---|---|---|---|---|---|---|
| E10.1 | Xác nhận điều kiện dự thi và đăng ký đội | Đã đăng ký trước 11/10 | Must | 0,1 | M1 | — |
| E10.2 | Kịch bản demo 3 phút | Team đã duyệt | Must | 0,5 | M3 | M2 |
| E10.3 | Quay và dựng video (cuộc gọi tiếng Anh + tiếng Việt) | Video 3 phút hoàn chỉnh | Must | 1,5 | M4 | E10.2 |
| E10.4 | Pitch deck / proposal | Nêu đủ vấn đề, giải pháp, bằng chứng, đối thủ, lộ trình | Must | 1,5 | M4 | E9.1–E9.5 |
| E10.5 | README + sơ đồ kiến trúc | Người ngoài clone về là chạy được theo README | Must | 0,5 | M4 | E1.2 |
| E10.6 | Chạy thử toàn bộ và nộp bài | Nộp trước hạn, đã kiểm tra lại link | Must | 0,5 | M4 | Toàn bộ |

---

## Gợi ý cấu hình GitHub Projects

| Thành phần | Thiết lập |
|---|---|
| Phân cấp | Epic = issue cha; Sub-epic = sub-issue của epic |
| Labels | `epic`, `sub-epic` + các label `area:*` ở đầu file |
| Milestones | M1 (9/10), M2 (13/10), M3 (16/10), M4 (18/10) |
| Custom fields | **Status:** Backlog → In progress → In review → Done<br>**Priority:** Must / Should / Could<br>**Estimate:** số ngày công |
| Views | **Board** theo Status · **Table** nhóm theo Epic · **Roadmap** theo Milestone |
| Phụ thuộc | Ghi mục "Phụ thuộc" vào mô tả của từng issue |
