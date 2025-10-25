# Dijitalleşme Asistanı - Frontend

React tabanlı belge dijitalleştirme kullanıcı arayüzü.

## Özellikler

- 🎨 Modern ve responsive tasarım (Tailwind CSS)
- 📤 Sürükle-bırak dosya yükleme
- 🔄 Gerçek zamanlı işlem durumu takibi
- ✅ AI tabanlı alan eşleştirme doğrulama
- 📊 Şablon ve toplu işlem yönetimi
- 🌐 Türkçe arayüz

## Kurulum

### 1. Bağımlılıkları Yükleyin

```bash
cd frontend
npm install
```

### 2. Ortam Değişkenleri (Opsiyonel)

`.env` dosyası oluşturun:

```
REACT_APP_API_URL=http://localhost:8000
```

Varsayılan olarak `http://localhost:8000` kullanılır.

## Çalıştırma

### Geliştirme Modu

```bash
npm start
```

Uygulama http://localhost:3000 adresinde açılacaktır.

### Production Build

```bash
npm run build
```

Build dosyaları `build/` klasöründe oluşturulur.

## Proje Yapısı

```
frontend/
├── public/
│   └── index.html
├── src/
│   ├── components/
│   │   ├── WelcomeWizard.jsx    # Yeni şablon oluşturma sihirbazı
│   │   ├── FieldMapper.jsx      # AI eşleştirme doğrulama
│   │   ├── BatchUpload.jsx      # Toplu dosya yükleme ve işleme
│   │   └── Dashboard.jsx        # Ana sayfa ve şablon yönetimi
│   ├── api.js                   # Backend API entegrasyonu
│   ├── App.jsx                  # Ana uygulama
│   ├── index.jsx                # React giriş noktası
│   └── index.css                # Global stiller
├── package.json
└── tailwind.config.js
```

## Kullanım Akışı

### 1. Yeni Şablon Oluşturma

1. "Yeni Şablon" butonuna tıklayın
2. Örnek bir belge yükleyin (PDF/Image)
3. Excel şablonunuzu yükleyin (sütun başlıkları = alanlar)
4. "Analiz Et" butonuna basın

### 2. Alan Eşleştirme

1. AI tarafından çıkarılan değerleri gözden geçirin
2. Düşük güven skoruna sahip alanları düzeltin
3. Şablona bir isim verin
4. "Şablonu Kaydet" butonuna basın

### 3. Toplu İşlem

1. Ana sayfadan bir şablon seçin
2. İşlemek istediğiniz belgeleri yükleyin
3. "Dosyaları İşle" butonuna basın
4. İşlem tamamlandığında Excel dosyasını indirin

## Bileşenler

### WelcomeWizard

Yeni şablon oluşturma sihirbazı. Kullanıcıdan örnek belge ve Excel şablonu alır, ardından AI analizi başlatır.

### FieldMapper

AI tarafından çıkarılan verileri görselleştirir. Kullanıcı düşük güven skoruna sahip alanları düzeltebilir.

### BatchUpload

Toplu belge yükleme ve işleme. Gerçek zamanlı ilerleme göstergesi ile işlem durumunu takip eder.

### Dashboard

Ana kontrol paneli. Şablonları listeler, istatistikler gösterir ve yeni işlemler başlatır.

## API Entegrasyonu

`src/api.js` dosyası tüm backend API çağrılarını içerir:

- `uploadSampleDocument()` - Örnek belge yükleme
- `uploadTemplateFile()` - Excel şablonu yükleme
- `analyzeDocument()` - AI analizi başlatma
- `saveTemplate()` - Şablon kaydetme
- `startBatchProcessing()` - Toplu işlem başlatma
- `getBatchStatus()` - İşlem durumu sorgulama
- `exportBatchResults()` - Excel dışa aktarma

## Stil ve Tema

Tailwind CSS kullanılmaktadır. Özel renkler ve sınıflar `tailwind.config.js` ve `index.css` dosyalarında tanımlanmıştır.

### Özel Sınıflar

- `.card` - Beyaz arka planlı kart
- `.btn` - Temel buton
- `.btn-primary` - Ana buton (mavi)
- `.btn-secondary` - İkincil buton (gri)
- `.btn-success` - Başarı butonu (yeşil)
- `.input` - Form input
- `.dropzone` - Sürükle-bırak alanı

## Sorun Giderme

### Backend'e bağlanamıyor

- Backend'in çalıştığından emin olun (`http://localhost:8000`)
- `.env` dosyasında `REACT_APP_API_URL` değerini kontrol edin
- CORS ayarlarının doğru olduğundan emin olun

### Build hataları

```bash
rm -rf node_modules package-lock.json
npm install
```

## Lisans

MIT
