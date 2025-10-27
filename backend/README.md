# Dijitalleşme Asistanı - Backend

FastAPI tabanlı belge dijitalleştirme ve veri çıkarma API'si. Türkçe ve İngilizce belgelerdeki özel karakterleri koruyarak iki dilde tutarlı sonuçlar üretmek üzere tasarlanmıştır.

## Özellikler

- 📄 PDF ve görüntü dosyalarından OCR ile metin çıkarma
- 🤖 OPENAI_MODEL ortam değişkeniyle seçilebilen OpenAI modelleri (varsayılan `gpt-5`) ile akıllı alan eşleştirme
- 📊 Excel şablonları ile özelleştirilebilir veri çıkarma
- 🔄 Toplu belge işleme
- 📈 Güven skorları ve doğrulama sistemi
- 🌐 Türkçe ve İngilizce belgeler için tam UTF-8 karakter desteği ile gelişmiş dil işleme
- 📁 Excel formatında dışa aktarma

## Gereksinimler

- Python 3.13+
- Tesseract OCR
- OpenAI API Key

## Kurulum

### 1. Python Bağımlılıkları

```bash
cd backend
pip install -r requirements.txt
```

### 2. Tesseract OCR Kurulumu

**Windows:**
1. [Tesseract Installer](https://github.com/UB-Mannheim/tesseract/wiki) adresinden yükleyiciyi indirin
2. Kurulum sırasında Türkçe dil paketini seçin
3. `.env` dosyasında Tesseract yolunu ayarlayın

**Linux:**
```bash
sudo apt-get install tesseract-ocr
sudo apt-get install tesseract-ocr-tur
```

**macOS:**
```bash
brew install tesseract
brew install tesseract-lang
```

### 3. Ortam Değişkenleri

`.env.example` dosyasını `.env` olarak kopyalayın ve düzenleyin. `OPENAI_MODEL` değişkeniyle erişebildiğiniz sohbet modelini seçebilir, varsayılan `gpt-5` değerini kullanabilirsiniz:

```bash
cp ../.env.example .env
```

Gerekli ayarlar:
```
OPENAI_API_KEY=your_api_key_here
OPENAI_MODEL=gpt-5
TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe  # Windows
```

### 4. Veritabanı Oluşturma

Uygulama ilk çalıştırıldığında otomatik olarak SQLite veritabanı oluşturulur.

## Çalıştırma

### Geliştirme Modu

```bash
uvicorn app.main:app --reload
```

veya

```bash
python -m app.main
```

API şu adreste çalışacaktır: http://localhost:8000

### API Dokümantasyonu

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## API Endpoints

### Upload
- `POST /api/upload/sample` - Örnek belge yükleme
- `POST /api/upload/template` - Excel şablonu yükleme
- `POST /api/upload/batch` - Toplu dosya yükleme

### Template
- `POST /api/template/analyze` - Belge analizi ve alan eşleştirme
- `POST /api/template/save` - Şablon kaydetme
- `POST /api/template/test` - Şablon testi
- `GET /api/template/list` - Şablon listesi
- `GET /api/template/{id}` - Şablon detayı
- `DELETE /api/template/{id}` - Şablon silme

#### Şablon Alan Yapısı
`target_fields` koleksiyonundaki her alan için kullanılan anahtarlar:

- `processing_mode` – OCR/LLM işleme stratejisini belirtir (`auto`, `ocr`, `llm` gibi değerler). Varsayılan `auto`.
- `llm_tier` – Alanın hangi LLM katmanında işleneceğini tanımlar (varsayılan `standard`).
- `handwriting_threshold` – El yazısı algılama eşiği (0 ile 1 arasında ondalık bir değer). Boş bırakılabilir.
- `auto_detected_handwriting` – Sistem tarafından alanın el yazısı olarak işaretlenip işaretlenmediğini belirtir (varsayılan `false`).

### Batch
- `POST /api/batch/start` - Toplu işlem başlatma
- `GET /api/batch/status/{id}` - İşlem durumu
- `GET /api/batch/list` - Toplu işlem listesi
- `DELETE /api/batch/{id}` - Toplu işlem silme

### Export
- `GET /api/export/batch/{id}` - Toplu işlem sonuçlarını Excel olarak indir
- `GET /api/export/validation/{id}` - Doğrulama raporunu indir
- `GET /api/export/template/{id}` - Boş şablon Excel dosyası indir
- `GET /api/export/document/{id}` - Tek belge sonucunu indir

## Proje Yapısı

```
backend/
├── app/
│   ├── main.py              # FastAPI uygulaması
│   ├── config.py            # Yapılandırma
│   ├── database.py          # Veritabanı modelleri
│   ├── models.py            # Pydantic modelleri
│   ├── core/
│   │   ├── image_processor.py    # Görüntü ön işleme
│   │   ├── ocr_engine.py         # Tesseract wrapper
│   │   ├── ai_field_mapper.py    # OpenAI entegrasyonu
│   │   ├── template_manager.py   # Şablon yönetimi
│   │   └── export_manager.py     # Excel dışa aktarma
│   └── routes/
│       ├── upload.py        # Yükleme endpoints
│       ├── template.py      # Şablon endpoints
│       ├── batch.py         # Toplu işlem endpoints
│       └── export.py        # Dışa aktarma endpoints
├── uploads/                 # Yüklenen dosyalar
├── outputs/                 # Oluşturulan dosyalar
└── requirements.txt
```

## Geliştirme

### Logging

Loglar hem konsola hem de `app.log` dosyasına yazılır:

```python
import logging
logger = logging.getLogger(__name__)
logger.info("Bilgi mesajı")
logger.error("Hata mesajı")
```

### Veritabanı

SQLite veritabanı `digitalization.db` dosyasında saklanır. Şema:
- `templates` - Şablon tanımları
- `template_fields` - Şablon alanları
- `batch_jobs` - Toplu işlem kayıtları
- `documents` - Yüklenen belgeler
- `extracted_data` - Çıkarılan veriler

### Testing

```bash
pytest
```

## Sorun Giderme

### Tesseract Bulunamadı
- Windows'ta `.env` dosyasında `TESSERACT_CMD` yolunu kontrol edin
- Linux/Mac'te `which tesseract` komutu ile yolu bulun

### OpenAI API Hatası
- `.env` dosyasında `OPENAI_API_KEY` değerinin doğru olduğundan emin olun
- API kotanızı kontrol edin

### UTF-8 Kodlama Hataları
- Tüm Python dosyaları `# -*- coding: utf-8 -*-` ile başlar
- Veritabanı bağlantısı UTF-8 destekler

## Lisans

MIT
