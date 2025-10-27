import React, { useState } from 'react';
import { useDropzone } from 'react-dropzone';
import { toast } from 'react-toastify';
import {
  uploadSampleDocument,
  uploadTemplateFile,
  analyzeDocument,
  createTemplate,
  updateTemplateFields,
} from '../api';

const WelcomeWizard = ({ onComplete }) => {
  const [step, setStep] = useState(1);
  const [sampleDoc, setSampleDoc] = useState(null);
  const [templateFile, setTemplateFile] = useState(null);
  const [documentId, setDocumentId] = useState(null);
  const [templateId, setTemplateId] = useState(null);
  const [templateFields, setTemplateFields] = useState([]);
  const [templateName, setTemplateName] = useState('Yeni Şablon');
  const [loading, setLoading] = useState(false);

  const hasEnabledFields = templateFields.some(field => field.enabled !== false);
  const allFieldsSelected = templateFields.length > 0 && templateFields.every(field => field.enabled !== false);

  const normalizeFieldDefaults = (field) => ({
    ...field,
    enabled: field?.enabled !== false,
    processing_mode: field?.processing_mode ? String(field.processing_mode).trim().toLowerCase() : 'auto',
    llm_tier: field?.llm_tier ? String(field.llm_tier).trim().toLowerCase() : 'standard',
    handwriting_threshold: (() => {
      if (
        field?.handwriting_threshold === undefined ||
        field?.handwriting_threshold === null ||
        field?.handwriting_threshold === ''
      ) {
        return null;
      }

      const numeric = Number(field.handwriting_threshold);
      return Number.isFinite(numeric) ? Math.min(1, Math.max(0, numeric)) : null;
    })(),
    auto_detected_handwriting: field?.auto_detected_handwriting === undefined
      ? false
      : Boolean(field.auto_detected_handwriting),
    regex_hint:
      field?.regex_hint === undefined || field?.regex_hint === null
        ? ''
        : field.regex_hint,
  });

  const updateTemplateField = (index, updates) => {
    const processed = { ...updates };

    if (Object.prototype.hasOwnProperty.call(processed, 'data_type')) {
      processed.data_type = processed.data_type ? String(processed.data_type).trim() : 'text';
    }

    if (Object.prototype.hasOwnProperty.call(processed, 'enabled')) {
      processed.enabled = processed.enabled !== false;
      if (processed.enabled === false) {
        processed.required = false;
      }
    }

    if (Object.prototype.hasOwnProperty.call(processed, 'required')) {
      processed.required = Boolean(processed.required);
    }

    setTemplateFields(prev =>
      prev.map((field, idx) =>
        idx === index
          ? normalizeFieldDefaults({
              ...field,
              ...processed,
            })
          : field
      )
    );
  };

  const toggleSelectAllFields = (enabled) => {
    setTemplateFields(prev =>
      prev.map(field =>
        normalizeFieldDefaults({
          ...field,
          enabled,
          required: enabled ? true : false,
        })
      )
    );
  };

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
      const normalizedFields = result.fields.map(field => normalizeFieldDefaults(field));

      setTemplateFields(normalizedFields);

      const derivedName = file.name
        ? file.name.replace(/\.[^/.]+$/, '').trim() || 'Yeni Şablon'
        : 'Yeni Şablon';

      setTemplateName(derivedName);

      // Create template in database
      const template = await createTemplate(
        derivedName || 'Yeni Şablon',
        normalizedFields,
        {}
      );
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
      if (result.error) {
        toast.warn(`AI eşleme sırasında hata: ${result.error}`);
      } else {
        toast.success('Analiz tamamlandı!');
      }

      // Pass results to next step
      const normalizedFields = templateFields.map(field => normalizeFieldDefaults(field));
      setTemplateFields(normalizedFields);
      onComplete({
        documentId,
        templateId,
        templateFields: normalizedFields,
        templateName,
        analysisResult: result,
      });
    } catch (error) {
      toast.error('Analiz hatası: ' + (error.response?.data?.detail || error.message));
    } finally {
      setLoading(false);
    }
  };

  const handlePrepareAnalysis = async () => {
    if (!templateId) {
      toast.error('Şablon oluşturulamadı');
      return;
    }

    setLoading(true);

    try {
      if (templateFields.length > 0) {
        const trimmedName = templateName.trim();
        const effectiveName = trimmedName || 'Yeni Şablon';
        setTemplateName(effectiveName);
        const normalizedFields = templateFields.map(field => normalizeFieldDefaults(field));
        setTemplateFields(normalizedFields);
        await updateTemplateFields(templateId, normalizedFields, effectiveName);
      }

      toast.success('Alan ayarları kaydedildi');
      setStep(3);
    } catch (error) {
      toast.error('Alan ayarları kaydedilemedi: ' + (error.response?.data?.detail || error.message));
    } finally {
      setLoading(false);
    }
  };

  const sampleDropzone = useDropzone({
    onDrop: onDropSample,
    accept: {
      'application/pdf': ['.pdf'],
      'image/jpeg': ['.jpg', '.jpeg'],
      'image/png': ['.png'],
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'],
      'application/vnd.ms-excel': ['.xls'],
      'text/csv': ['.csv']
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
            Sisteme öğretmek için bir örnek belge yükleyin (PDF, JPG, PNG veya Excel)
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
                <p className="text-sm text-gray-400 mt-2">PDF, JPG, PNG, XLSX, XLS, CSV (Maks. 10MB)</p>
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
            <div className="mt-4">
              <div className="mb-4">
                <label className="block text-sm font-medium text-gray-700 mb-1">Şablon Adı</label>
                <input
                  type="text"
                  className="border rounded px-3 py-2 w-full"
                  value={templateName}
                  onChange={(e) => setTemplateName(e.target.value)}
                  placeholder="Örn: Fatura Şablonu"
                />
              </div>
              <h3 className="font-medium mb-2">Bulunan Alanlar</h3>
              <div className="flex items-center justify-between mb-2">
                <label className="inline-flex items-center gap-2 text-sm font-medium text-gray-700">
                  <input
                    type="checkbox"
                    className="rounded"
                    checked={allFieldsSelected}
                    onChange={(e) => toggleSelectAllFields(e.target.checked)}
                  />
                  <span>Tümünü Seç</span>
                </label>
                <span className="text-xs text-gray-500">
                  {hasEnabledFields
                    ? 'İşaretli alanlar analizde kullanılacak.'
                    : 'Analize dahil edilecek alan seçimi yapın.'}
                </span>
              </div>
              <div className="overflow-x-auto border border-gray-200 rounded-lg">
                <table className="min-w-full divide-y divide-gray-200">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                        Dahil Et
                      </th>
                      <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                        Alan Adı
                      </th>
                      <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                        Veri Tipi
                      </th>
                      <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                        Gerekli
                      </th>
                    </tr>
                  </thead>
                  <tbody className="bg-white divide-y divide-gray-200 text-sm">
                    {templateFields.map((field, index) => (
                      <tr key={field.field_name} className={!field.enabled ? 'opacity-60' : ''}>
                        <td className="px-4 py-2 align-middle">
                          <input
                            type="checkbox"
                            className="rounded"
                            checked={field.enabled !== false}
                            onChange={(e) =>
                              updateTemplateField(index, { enabled: e.target.checked })
                            }
                          />
                        </td>
                        <td className="px-4 py-2 align-middle font-medium text-gray-700">
                          {field.field_name}
                        </td>
                        <td className="px-4 py-2 align-middle">
                          <select
                            className="border rounded px-2 py-1 w-full"
                            value={field.data_type || 'text'}
                            onChange={(e) =>
                              updateTemplateField(index, { data_type: e.target.value })
                            }
                          >
                            <option value="text">Metin</option>
                            <option value="number">Sayı</option>
                            <option value="date">Tarih</option>
                          </select>
                        </td>
                        <td className="px-4 py-2 align-middle">
                          <input
                            type="checkbox"
                            className="rounded"
                            checked={field.required || false}
                            onChange={(e) =>
                              updateTemplateField(index, { required: e.target.checked })
                            }
                          />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="text-xs text-gray-500 mt-2">
                Analize sadece işaretli alanlar dahil edilir.
              </p>
              {!hasEnabledFields && (
                <p className="text-sm text-red-600 mt-2">
                  En az bir alan seçmeden devam edemezsiniz.
                </p>
              )}
            </div>
          )}

          <div className="flex gap-3 mt-4">
            <button
              onClick={() => setStep(1)}
              className="flex-1 bg-gray-200 text-gray-700 py-3 rounded-lg font-medium hover:bg-gray-300 transition-colors disabled:bg-gray-300 disabled:text-gray-500"
              disabled={loading}
            >
              Geri
            </button>
            {templateFile && templateId && (
              <button
                onClick={handlePrepareAnalysis}
                className="flex-1 bg-blue-600 text-white py-3 rounded-lg font-medium hover:bg-blue-700 transition-colors disabled:bg-gray-400"
                disabled={loading || !hasEnabledFields}
              >
                {loading ? 'Kaydediliyor...' : 'Devam Et'}
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
            <div className="flex items-center justify-between mb-2">
              <span className="text-gray-600">Şablon Adı:</span>
              <span className="font-medium">{templateName}</span>
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
              disabled={loading || !hasEnabledFields}
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
          {!hasEnabledFields && (
            <p className="text-sm text-red-600 mt-3">
              Analizi başlatmak için en az bir alan seçmelisiniz.
            </p>
          )}
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
