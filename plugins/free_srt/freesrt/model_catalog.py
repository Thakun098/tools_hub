"""Whisper model metadata shown by the API and frontend."""

MODELS_INFO = {
    "ggml-base.bin": {
        "name": "Base", "url": "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.bin", "size": "148 MB",
        "description": "ทำงานเร็วและใช้ทรัพยากรน้อย เหมาะสำหรับทดลองหรือไฟล์เสียงที่ชัดเจน", "speed": "เร็วมาก", "accuracy": "พื้นฐาน",
        "recommended_for": "ทดลองใช้งาน คลิปสั้น และเครื่องสเปกไม่สูง", "memory_hint": "ใช้หน่วยความจำน้อย", "badge": "เบาและเร็ว"},
    "ggml-small.bin": {
        "name": "Small", "url": "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.bin", "size": "466 MB",
        "description": "สมดุลระหว่างความเร็วและความแม่นยำ เหมาะกับงานทั่วไปบนคอมพิวเตอร์ส่วนใหญ่", "speed": "เร็ว", "accuracy": "ดี",
        "recommended_for": "งานตัดต่อทั่วไปและคลิปที่เสียงค่อนข้างชัด", "memory_hint": "ใช้หน่วยความจำปานกลาง", "badge": "เครื่องทั่วไป"},
    "ggml-medium.bin": {
        "name": "Medium", "url": "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-medium.bin", "size": "1.5 GB",
        "description": "แม่นยำขึ้นสำหรับเสียงที่ฟังยากหรือหลายภาษา แต่ใช้เวลาประมวลผลนานขึ้น", "speed": "ปานกลาง", "accuracy": "สูง",
        "recommended_for": "งานจริงที่ต้องการความแม่นยำเพิ่มขึ้น", "memory_hint": "ควรมี RAM ว่างอย่างน้อยประมาณ 3 GB", "badge": "แม่นยำสูง"},
    "ggml-large-v3-turbo.bin": {
        "name": "Large v3 Turbo", "url": "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo.bin", "size": "1.6 GB",
        "description": "ความแม่นยำสูงและเร็วกว่า Large v3 เหมาะกับงานภาษาไทยและงานตัดต่อจริง", "speed": "ค่อนข้างเร็ว", "accuracy": "สูงมาก",
        "recommended_for": "งานภาษาไทยและงานประจำวันบนเครื่องระดับกลางถึงสูง", "memory_hint": "ควรมี RAM ว่างอย่างน้อยประมาณ 4 GB", "badge": "แนะนำ"},
    "ggml-large-v3.bin": {
        "name": "Large v3", "url": "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3.bin", "size": "3.1 GB",
        "description": "เน้นความแม่นยำสูงสุด แต่ช้าและใช้ทรัพยากรมาก เหมาะกับงานสำคัญที่ยอมรอได้", "speed": "ช้า", "accuracy": "สูงสุด",
        "recommended_for": "เสียงยาก งานหลายภาษา และงานที่เน้นคุณภาพ", "memory_hint": "ควรมี RAM ว่างอย่างน้อยประมาณ 6 GB", "badge": "คุณภาพสูงสุด"},
}
