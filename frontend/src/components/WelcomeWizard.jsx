import React, { useState } from 'react';
import { useDropzone } from 'react-dropzone';
import { toast } from 'react-toastify';
import { uploadSampleDocument, uploadTemplateFile, analyzeDocument, createTemplate } from '../api';

const WelcomeWizard = ({ onComplete }) => {
  const [step, setStep] = useState(1);
  const [sampleDoc, setSampleDoc] = useState(null);
  const [templateFile, setTemplateFile] = useState(null);
  const [documentId, setDocumentId] = useState(null);
  const [templateId, setTemplateId] = useState(null);
  const [templateFields, setTemplateFields] = useState([]);
  const [loading, setLoading] = useState(false);

  // Step 1: Upload sample document
  const onDropSample = async (acceptedFiles) => {
    if (acceptedFiles.length === 0) return;

    const file = acceptedFiles[0];
    setSampleDoc(file);
    setLoading(true);

    try {
      const result = await uploadSampleDocument(file);
      setDocumentId(result.document_id);
      toast.success('Örnek belge yüklendi!');
    } catch (error) {
      toast.error('Belge yükleme hatası: ' + (error.response?.data?.detail || error.message));
    } finally {
      setLoading(false);
    }
  };

  // Step 2: Upload template file
  const onDropTemplate = async (acceptedFiles) => {
    if (acceptedFiles.length === 0) {
      toast.warning('Lütfen bir Excel dosyası seçin (.xlsx, .xls veya .csv)');
      return;
    }

    const file = acceptedFiles[0];
    
    // Manual file type check
    const fileName = file.name.toLowerCase();
    if (!fileName.endsWith('.xlsx') && !fileName.endsWith('.xls') && !fileName.endsWith('.csv')) {
      toast.error('Sadece Excel dosyaları kabul edilir (.xlsx, .xls, .csv)');
      return;
    }

    setTemplateFile(file);
    setLoading(true);

    try {
      const result = await uploadTemplateFile(file);
      setTemplateFields(result.fields);

      // Create template in database
      const template = await createTemplate('Yeni Şablon', result.fields, {});
      setTemplateId(template.id);

      toast.success(`Excel şablonu yüklendi! ${result.field_count} alan bulundu.`);
    } catch (error) {
      toast.error('Şablon yükleme hatası: ' + (error.response?.data?.detail || error.message));
    } finally {
      setLoading(false);
    }
  };

  // Analyze document
  const handleAnalyze = async () => {
    if (!documentId || !templateId) {
      toast.error('Önce belge ve şablon yükleyin');
      return;
    }

    setLoading(true);

    try {
      const result = await analyzeDocument(documentId, templateId);
      toast.success('Analiz tamamlandı!');

      // Pass results to next step
      onComplete({
        documentId,
        templateId,
        templateFields,
        analysisResult: result,
      });
    } catch (error) {
      toast.error('Analiz hatası: ' + (error.response?.data?.detail || error.message));
    } finally {
      setLoading(false);
    }
  };

  const sampleDropzone = useDropzone({
    onDrop: onDropSample,
    accept: {
      'application/pdf': ['.pdf'],
      'image/jpeg': ['.jpg', '.jpeg'],
      'image/png': ['.png']
    },
    maxFiles: 1,
    multiple: false
  });

  const templateDropzone = useDropzone({
    onDrop: onDropTemplate,
    accept: {
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'],
      'application/vnd.ms-excel': ['.xls'],
      'text/csv': ['.csv']
    },
    maxFiles: 1,
    multiple: false,
    noClick: false,
    noKeyboard: false
  });

  return (
    <div className="max-w-4xl mx-auto p-6">
      <h1 className="text-3xl font-bold text-gray-800 mb-2">Dijitalleşme Asistanı</h1>
      <p className="text-gray-600 mb-8">Belgelerinizi otomatik olarak dijitalleştirin</p>

      {/* Progress indicator */}
      <div className="flex items-center justify-center mb-8">
        <div className="flex items-center">
          <div className={`w-10 h-10 rounded-full flex items-center justify-center ${step >= 1 ? 'bg-blue-600 text-white' : 'bg-gray-300'}`}>
            1
          </div>
          <div className={`w-24 h-1 ${step >= 2 ? 'bg-blue-600' : 'bg-gray-300'}`}></div>
          <div className={`w-10 h-10 rounded-full flex items-center justify-center ${step >= 2 ? 'bg-blue-600 text-white' : 'bg-gray-300'}`}>
            2
          </div>
          <div className={`w-24 h-1 ${step >= 3 ? 'bg-blue-600' : 'bg-gray-300'}`}></div>
          <div className={`w-10 h-10 rounded-full flex items-center justify-center ${step >= 3 ? 'bg-blue-600 text-white' : 'bg-gray-300'}`}>
            3
          </div>
        </div>
      </div>

      {/* Step 1: Upload Sample Document */}
      {step === 1 && (
        <div className="bg-white shadow-lg rounded-lg p-6">
          <h2 className="text-2xl font-semibold mb-4">Adım 1: Örnek Belge Yükleyin</h2>
          <p className="text-gray-600 mb-4">
            Sisteme öğretmek için bir örnek belge yükleyin (PDF, JPG veya PNG)
          </p>

          <div
            {...sampleDropzone.getRootProps()}
            className={`border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors ${
              sampleDropzone.isDragActive 
                ? 'border-blue-500 bg-blue-50' 
                : 'border-gray-300 hover:border-blue-400'
            }`}
          >
            <input {...sampleDropzone.getInputProps()} />
            {sampleDoc ? (
              <div>
                <p className="text-green-600 font-medium">✓ {sampleDoc.name}</p>
                <p className="text-sm text-gray-500">{(sampleDoc.size / 1024).toFixed(2)} KB</p>
              </div>
            ) : (
              <div>
                <p className="text-gray-600">Belgeyi buraya sürükleyin veya tıklayın</p>
                <p className="text-sm text-gray-400 mt-2">PDF, JPG, PNG (Maks. 10MB)</p>
              </div>
            )}
          </div>

          {sampleDoc && documentId && (
            <button
              onClick={() => setStep(2)}
              className="mt-4 w-full bg-blue-600 text-white py-3 rounded-lg font-medium hover:bg-blue-700 transition-colors"
            >
              Devam Et
            </button>
          )}
        </div>
      )}

      {/* Step 2: Upload Template */}
      {step === 2 && (
        <div className="bg-white shadow-lg rounded-lg p-6">
          <h2 className="text-2xl font-semibold mb-4">Adım 2: Excel Şablonu Yükleyin</h2>
          <p className="text-gray-600 mb-4">
            Çıkarmak istediğiniz alanları içeren Excel şablonunu yükleyin
          </p>

          <div
            {...templateDropzone.getRootProps()}
            className={`border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors ${
              templateDropzone.isDragActive 
                ? 'border-green-500 bg-green-50' 
                : 'border-gray-300 hover:border-green-400'
            }`}
          >
            <input {...templateDropzone.getInputProps()} />
            {templateFile ? (
              <div>
                <p className="text-green-600 font-medium">✓ {templateFile.name}</p>
                <p className="text-sm text-gray-500">{templateFields.length} alan bulundu</p>
              </div>
            ) : (
              <div>
                <p className="text-gray-600">Excel dosyasını buraya sürükleyin veya tıklayın</p>
                <p className="text-sm text-gray-400 mt-2">XLSX, XLS, CSV</p>
              </div>
            )}
          </div>

          {templateFields.length > 0 && (
            <div className="mt-4 p-4 bg-gray-50 rounded-lg">
              <h3 className="font-medium mb-2">Bulunan Alanlar:</h3>
              <div className="flex flex-wrap gap-2">
                {templateFields.map((field, idx) => (
                  <span key={idx} className="px-3 py-1 bg-blue-100 text-blue-700 rounded-full text-sm">
                    {field.field_name}
                  </span>
                ))}
              </div>
            </div>
          )}

          <div className="flex gap-3 mt-4">
            <button
              onClick={() => setStep(1)}
              className="flex-1 bg-gray-200 text-gray-700 py-3 rounded-lg font-medium hover:bg-gray-300 transition-colors"
            >
              Geri
            </button>
            {templateFile && templateId && (
              <button
                onClick={() => setStep(3)}
                className="flex-1 bg-blue-600 text-white py-3 rounded-lg font-medium hover:bg-blue-700 transition-colors"
              >
                Devam Et
              </button>
            )}
          </div>
        </div>
      )}

      {/* Step 3: Analyze */}
      {step === 3 && (
        <div className="bg-white shadow-lg rounded-lg p-6">
          <h2 className="text-2xl font-semibold mb-4">Adım 3: Analiz Et</h2>
          <p className="text-gray-600 mb-4">
            Belge ve şablon hazır. AI ile analiz etmeye başlayın.
          </p>

          <div className="bg-gray-50 p-4 rounded-lg mb-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-gray-600">Örnek Belge:</span>
              <span className="font-medium">{sampleDoc?.name}</span>
            </div>
            <div className="flex items-center justify-between mb-2">
              <span className="text-gray-600">Excel Şablonu:</span>
              <span className="font-medium">{templateFile?.name}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-gray-600">Alan Sayısı:</span>
              <span className="font-medium">{templateFields.length}</span>
            </div>
          </div>

          <div className="flex gap-3">
            <button
              onClick={() => setStep(2)}
              className="flex-1 bg-gray-200 text-gray-700 py-3 rounded-lg font-medium hover:bg-gray-300 transition-colors"
              disabled={loading}
            >
              Geri
            </button>
            <button
              onClick={handleAnalyze}
              className="flex-1 bg-blue-600 text-white py-3 rounded-lg font-medium hover:bg-blue-700 transition-colors disabled:bg-gray-400"
              disabled={loading}
            >
              {loading ? (
                <span className="flex items-center justify-center">
                  <svg className="animate-spin h-5 w-5 mr-2" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none"></circle>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                  Analiz Ediliyor...
                </span>
              ) : (
                'Analiz Et'
              )}
            </button>
          </div>
        </div>
      )}

      {loading && step !== 3 && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white p-6 rounded-lg">
            <svg className="animate-spin h-10 w-10 mx-auto mb-4 text-blue-600" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none"></circle>
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
            </svg>
            <p className="text-gray-700">Yükleniyor...</p>
          </div>
        </div>
      )}
    </div>
  );
};

export default WelcomeWizard;
