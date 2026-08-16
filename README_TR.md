# YouTube Altyazı & Ekran Görüntüsü OCR Sohbet Robotu (Transkriptör Chat)

[English](README.md) | [Türkçe](README_TR.md)

YouTube videolarından otomatik olarak altyazı çeken, arama yapan, ekran görüntülerinden akıllı çok sütunlu OCR (Optik Karakter Tanıma) gerçekleştiren ve modern, glassmorphic (cam tasarımlı) sohbet arayüzü ile tüm bu süreçleri yöneten güçlü bir Flask tabanlı masaüstü/web uygulamasıdır.

## 🚀 Özellikler

- **📺 YouTube Altyazı Çekici**: YouTube videolarının altyazılarını `youtube-transcript-api` (en güncel sürüm nesne yapıları ile uyumlu) kullanarak anında çeker.
- **📸 Akıllı Ekran Görüntüsü OCR**: Ekran görüntülerindeki veya video listelerindeki metinleri OCR.space Engine 2 entegrasyonuyla okur.
  - **Çoklu Video Sütun Analizi**: Yan yana duran video arama sonuç sütunlarını metin alanlarına göre otomatik olarak ayırır.
  - **Başlık Sınırı İzolatörü**: Video süreleri ve kanal adları gibi gürültü verileri eleyerek sadece video başlıklarını koordinat tabanlı tespit eder.
- **⚡ Eşzamanlı Pano Kopyalama**: Modern tarayıcıların (Brave, Chrome vb.) güvenlik engellerini, arka planda önbelleğe alınmış veri yönetimiyle aşarak tek tıkla panoya güvenli ve anında kopyalama sağlar.
- **💬 Glassmorphic İnteraktif Sohbet**: HTML5 ve CSS3'ün en modern özellikleriyle tasarlanmış, şık ve dinamik kullanıcı arayüzü.
- **🛠️ Bağımsız ve Taşınabilir Altyapı**: Python 3.11 üzerinde minimum kurulumla yerel olarak çalıştırılabilir.

## 🛠️ Teknoloji Yığını

- **Backend**: Python, Flask, `youtube-transcript-api`, `requests`, `yt-dlp`
- **Frontend**: Vanilla HTML5, CSS3 (Özel Cam Efekti Tasarım Sistemi), Javascript (ES6+)
- **Harici API**: Gelişmiş optik karakter tanıma için OCR.space API.

## ⚙️ Kurulum ve Çalıştırma

1. **Depoyu klonlayın**:
   ```bash
   git clone <depo-adresi>
   cd transkriptor-chat-app
   ```

2. **Gereksinimleri yükleyin**:
   ```bash
   pip install flask youtube-transcript-api requests yt-dlp
   ```

3. **OCR.space API Anahtarınızı alın**:
   - [ocr.space](https://ocr.space/ocrapi) adresinden ücretsiz bir API anahtarı alın.
   - Uygulama ayarları arayüzünden anahtarınızı girin veya `app.py` içindeki ilgili alanı düzenleyin.

4. **Uygulamayı başlatın**:
   ```bash
   python app.py
   ```
   - Tarayıcınızı açın ve `http://127.0.0.1:5000` adresine gidin.

## 📁 Dosya Yapısı

- `app.py`: Yönlendirmeleri, YouTube API işlemlerini, OCR işleme adımlarını ve altyazı önbellek yönetimini gerçekleştiren ana Flask uygulaması.
- `README.md`: İngilizce dökümantasyon.
- `README_TR.md`: Türkçe dökümantasyon.

---

*Emirhan Kaya tarafından sevgiyle tasarlandı ve geliştirildi. 💙*
