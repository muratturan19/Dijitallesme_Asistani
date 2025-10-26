# Dijitalleşme Asistanı

AI destekli belge dijitalleştirme ve veri çıkarma sistemi. Kullanıcılar bir örnek belge ve Excel şablonu yükleyerek sisteme "öğretir", ardından toplu belgeleri otomatik olarak işler. Sistem, Türkçe ve İngilizce belgelerdeki özel karakterleri doğru şekilde işleyerek iki dilde de güvenilir sonuçlar üretir.

## Özellikler

- 📄 **OCR ile Metin Çıkarma**: Tesseract kullanarak PDF ve görüntülerden metin çıkarma
- 🤖 **AI Tabanlı Alan Eşleştirme**: OPENAI_MODEL ortam değişkeniyle seçilebilen OpenAI modelleri (varsayılan `gpt-5`) ile akıllı alan tanıma
- 📊 **Özelleştirilebilir Şablonlar**: Excel şablonları ile kendi alanlarınızı tanımlayın
- 🔄 **Toplu İşleme**: Yüzlerce belgeyi aynı anda işleyin
- ✅ **Güven Skorları**: Düşük güvenilirlikte alanları gözden geçirin
- 📁 **Excel Dışa Aktarma**: Sonuçları Excel formatında indirin
- 🌐 **İki Dilli Destek**: Türkçe ve İngilizce belgeler için tam UTF-8 karakter desteği ve dil odaklı işleme yetenekleri

## Teknoloji Stack

### Backend
- **Framework**: Python 3.13, FastAPI
- **OCR**: Tesseract (pytesseract)
- **Görüntü İşleme**: Pillow, OpenCV
- **AI**: OPENAI_MODEL ortam değişkeniyle seçilen OpenAI sohbet modeli (varsayılan `gpt-5`)
- **Veritabanı**: SQLite (SQLAlchemy)
- **Excel**: openpyxl

### Frontend
- **Framework**: React (latest)
- **Styling**: Tailwind CSS
- **API Client**: Axios
- **Dosya Yükleme**: react-dropzone
- **Bildirimler**: react-toastify

## Hızlı Başlangıç

### Gereksinimler

- Python 3.13+
- Node.js 18+
- Tesseract OCR
- OpenAI API Key

### 1. Projeyi Klonlayın

```bash
git clone <repository-url>
cd Dijitallesme_Asistani
```

### 2. Ortam Değişkenlerini Ayarlayın

```bash
cp .env.example .env
```

`.env` dosyasını düzenleyin ve gerekli bilgileri girin. `OPENAI_MODEL` ayarı ile erişebildiğiniz OpenAI sohbet modelini seçebilir, varsayılan olarak `gpt-5` kullanabilirsiniz:

```env
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-5
TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe  # Windows
```

### 3. Backend Kurulumu

```bash
cd backend
pip install -r requirements.txt
```

**Tesseract Kurulumu (Windows):**
1. [Tesseract Installer](https://github.com/UB-Mannheim/tesseract/wiki) adresinden indirin
2. Kurulum sırasında Türkçe dil paketini seçin
3. `.env` dosyasında yolu ayarlayın

**Tesseract Kurulumu (Linux):**
```bash
sudo apt-get install tesseract-ocr tesseract-ocr-tur
```

**Backend'i Çalıştırın:**
```bash
uvicorn app.main:app --reload
```

Backend http://localhost:8000 adresinde çalışacaktır.

### 4. Frontend Kurulumu

```bash
cd frontend
npm install
npm start
```

Frontend http://localhost:3000 adresinde açılacaktır.

## Kullanım

### 1. Yeni Şablon Oluşturma

1. Frontend'de "Yeni Şablon Oluştur" butonuna tıklayın
2. **Adım 1**: Örnek bir belge yükleyin (PDF, JPG, PNG)
3. **Adım 2**: Excel şablonunuzu yükleyin (ilk satır = alan adları)
4. **Adım 3**: "Analiz Et" butonuna basın

### 2. Alan Eşleştirme

- AI otomatik olarak alanları eşleştirir
- Yeşil: Yüksek güven (>80%)
- Sarı: Orta güven (50-80%)
- Kırmızı: Düşük güven (<50%) - kontrol edin!
- Hatalı alanları manuel olarak düzeltin
- Şablonu kaydedin

### 3. Toplu İşleme

1. Ana sayfadan bir şablon seçin
2. İşlenecek belgeleri sürükleyip bırakın
3. "Dosyaları İşle" butonuna basın
4. İlerlemeyi takip edin
5. Tamamlandığında Excel dosyasını indirin

## Proje Yapısı

```
Dijitallesme_Asistani/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI uygulaması
│   │   ├── config.py            # Konfigürasyon
│   │   ├── database.py          # Veritabanı modelleri
│   │   ├── models.py            # Pydantic modelleri
│   │   ├── core/
│   │   │   ├── image_processor.py    # Görüntü ön işleme
│   │   │   ├── ocr_engine.py         # OCR motoru
│   │   │   ├── ai_field_mapper.py    # AI eşleştirme
│   │   │   ├── template_manager.py   # Şablon yönetimi
│   │   │   └── export_manager.py     # Excel dışa aktarma
│   │   └── routes/
│   │       ├── upload.py        # Dosya yükleme
│   │       ├── template.py      # Şablon işlemleri
│   │       ├── batch.py         # Toplu işlem
│   │       └── export.py        # Dışa aktarma
│   ├── uploads/                 # Yüklenen dosyalar
│   ├── outputs/                 # Oluşturulan Excel dosyaları
│   └── requirements.txt
│
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── WelcomeWizard.jsx     # Şablon oluşturma sihirbazı
│   │   │   ├── FieldMapper.jsx       # Alan eşleştirme
│   │   │   ├── BatchUpload.jsx       # Toplu yükleme
│   │   │   └── Dashboard.jsx         # Ana sayfa
│   │   ├── api.js               # API client
│   │   ├── App.jsx              # Ana uygulama
│   │   └── index.jsx
│   └── package.json
│
├── .env.example                 # Ortam değişkenleri şablonu
├── .gitignore
└── README.md
```

## API Dokümantasyonu

Backend çalışırken Swagger UI'ye erişin:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### Ana Endpointler

- `POST /api/upload/sample` - Örnek belge yükle
- `POST /api/upload/template` - Excel şablonu yükle
- `POST /api/template/analyze` - Belgeyi analiz et
- `POST /api/template/save` - Şablonu kaydet
- `POST /api/batch/start` - Toplu işlem başlat
- `GET /api/batch/status/{id}` - İşlem durumu
- `GET /api/export/batch/{id}` - Excel indir

## Özelleştirme

### Yeni Alan Tipleri Eklemek

`backend/app/core/template_manager.py` içinde `_infer_data_type()` fonksiyonunu düzenleyin.

### UI Renklerini Değiştirmek

`frontend/tailwind.config.js` dosyasında tema renklerini özelleştirin.

### OCR Dilini Değiştirmek

`.env` dosyasında veya `backend/app/config.py` içinde `TESSERACT_LANG` değişkenini düzenleyin.

## Sorun Giderme

### Tesseract Bulunamadı

**Windows**: `.env` dosyasında `TESSERACT_CMD` yolunu kontrol edin
**Linux/Mac**: `which tesseract` komutu ile yolu bulun ve `.env` dosyasında ayarlayın

### OpenAI API Hatası

- API anahtarınızı kontrol edin
- Hesap kotanızı kontrol edin
- İnternet bağlantınızı kontrol edin

### CORS Hatası

Backend'in `app/config.py` dosyasında `CORS_ORIGINS` listesine frontend URL'nizi ekleyin.

### Türkçe Karakter Sorunları

- Tüm dosyalar UTF-8 encoding ile kaydedilmelidir
- Tesseract'ın Türkçe dil paketi yüklü olmalıdır

## Performans İpuçları

- **Görüntü Kalitesi**: Daha iyi OCR için yüksek çözünürlüklü belgeler kullanın
- **Batch Size**: Bir seferde maksimum 100 dosya işleyin
- **API Rate Limit**: OpenAI rate limitlerini aşmamak için batch boyutunu ayarlayın

## Güvenlik

- `.env` dosyasını asla Git'e eklemeyin
- Production'da güçlü CORS politikaları kullanın
- API anahtarlarını güvenli saklayın
- Dosya yükleme boyutlarını sınırlayın (varsayılan: 10MB)

## Katkıda Bulunma

1. Fork edin
2. Feature branch oluşturun (`git checkout -b feature/amazing-feature`)
3. Commit edin (`git commit -m 'feat: Add amazing feature'`)
4. Push edin (`git push origin feature/amazing-feature`)
5. Pull Request açın

## Lisans

MIT

## Destek

Sorularınız için:
- GitHub Issues açın
- Dokümantasyonu kontrol edin
- Backend logs: `backend/app.log`

## Roadmap

- [ ] Çoklu dil desteği (İngilizce, Almanca, vb.)
- [ ] Cloud storage entegrasyonu (AWS S3, Google Drive)
- [ ] Webhook desteği
- [ ] REST API rate limiting
- [ ] Docker containerization
- [ ] Makine öğrenimi ile iyileştirme (kullanıcı düzeltmelerinden öğrenme)
- [ ] PDF form recognition
- [ ] Tablo çıkarma
- [ ] Handwriting recognition

## Sürüm Geçmişi

### v1.0.0 (2024)
- İlk sürüm
- Temel OCR ve AI eşleştirme
- Toplu işlem desteği
- Excel dışa aktarma