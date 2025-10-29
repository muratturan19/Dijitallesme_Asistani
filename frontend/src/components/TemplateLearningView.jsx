import React, { useEffect, useMemo, useState } from 'react';
import { toast } from 'react-toastify';
import {
  getTemplates,
  getTemplate,
  submitLearningCorrection,
  fetchLearnedHints,
  fetchCorrectionHistory,
  fetchLearningDocuments,
} from '../api';

const initialFormState = {
  documentId: '',
  templateFieldId: '',
  originalValue: '',
  correctedValue: '',
  context: '',
  userId: '',
};

const TemplateLearningView = ({ onBack, initialDocumentId, initialFieldId, initialTemplateId }) => {
  const [templates, setTemplates] = useState([]);
  const [selectedTemplateId, setSelectedTemplateId] = useState(
    initialTemplateId !== undefined && initialTemplateId !== null ? String(initialTemplateId) : ''
  );
  const [templateFields, setTemplateFields] = useState([]);
  const [selectedFieldId, setSelectedFieldId] = useState(
    initialFieldId !== undefined && initialFieldId !== null && initialFieldId !== ''
      ? String(initialFieldId)
      : ''
  );
  const [hints, setHints] = useState({});
  const [history, setHistory] = useState([]);
  const [documentOptions, setDocumentOptions] = useState([]);
  const [loadingDocuments, setLoadingDocuments] = useState(false);
  const [documentError, setDocumentError] = useState('');
  const [formState, setFormState] = useState(() => ({
    ...initialFormState,
    documentId:
      initialDocumentId !== undefined && initialDocumentId !== null && initialDocumentId !== ''
        ? String(initialDocumentId)
        : '',
    templateFieldId:
      initialFieldId !== undefined && initialFieldId !== null && initialFieldId !== ''
        ? String(initialFieldId)
        : '',
  }));
  const [sampleLimit, setSampleLimit] = useState(50);
  const [loadingTemplate, setLoadingTemplate] = useState(false);
  const [loadingHints, setLoadingHints] = useState(false);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    const loadTemplates = async () => {
      try {
        const data = await getTemplates();
        setTemplates(data);
      } catch (error) {
        toast.error('Şablonlar yüklenirken hata oluştu: ' + (error.response?.data?.detail || error.message));
      }
    };

    loadTemplates();
  }, []);

  useEffect(() => {
    if (initialTemplateId === undefined || initialTemplateId === null) {
      return;
    }
    setSelectedTemplateId(String(initialTemplateId));
  }, [initialTemplateId]);

  useEffect(() => {
    if (initialDocumentId === undefined || initialDocumentId === null) {
      return;
    }

    setFormState((prev) => ({
      ...prev,
      documentId:
        initialDocumentId === '' ? '' : String(initialDocumentId),
    }));
  }, [initialDocumentId]);

  const updateFieldSelection = (value) => {
    setSelectedFieldId(value);
    setFormState((prev) => ({ ...prev, templateFieldId: value }));
  };

  useEffect(() => {
    if (initialFieldId === undefined) {
      return;
    }

    if (initialFieldId === null || initialFieldId === '') {
      updateFieldSelection('');
      return;
    }

    updateFieldSelection(String(initialFieldId));
  }, [initialFieldId]);

  useEffect(() => {
    if (!selectedTemplateId) {
      setTemplateFields([]);
      setHints({});
      setHistory([]);
      setDocumentOptions([]);
      setDocumentError('');
      return;
    }

    const templateId = Number(selectedTemplateId);
    const loadTemplateDetails = async () => {
      setLoadingTemplate(true);
      try {
        const template = await getTemplate(templateId);
        setTemplateFields(template?.target_fields || []);
      } catch (error) {
        toast.error('Şablon bilgileri alınamadı: ' + (error.response?.data?.detail || error.message));
        setTemplateFields([]);
      } finally {
        setLoadingTemplate(false);
      }
    };

    loadTemplateDetails();
  }, [selectedTemplateId]);

  useEffect(() => {
    if (!selectedTemplateId) {
      setDocumentOptions([]);
      setDocumentError('');
      setLoadingDocuments(false);
      return;
    }

    let isActive = true;
    const loadDocuments = async () => {
      setLoadingDocuments(true);
      setDocumentError('');
      try {
        const data = await fetchLearningDocuments(Number(selectedTemplateId));
        if (!isActive) {
          return;
        }
        setDocumentOptions(Array.isArray(data) ? data : []);
      } catch (error) {
        if (!isActive) {
          return;
        }
        const message =
          'Belgeler yüklenirken hata oluştu: ' +
          (error.response?.data?.detail || error.message || 'Bilinmeyen hata');
        setDocumentError(message);
        setDocumentOptions([]);
        toast.error(message);
      } finally {
        if (isActive) {
          setLoadingDocuments(false);
        }
      }
    };

    loadDocuments();

    return () => {
      isActive = false;
    };
  }, [selectedTemplateId]);

  useEffect(() => {
    if (!selectedTemplateId) {
      setHints({});
      return;
    }

    const loadHints = async () => {
      setLoadingHints(true);
      try {
        const response = await fetchLearnedHints(Number(selectedTemplateId), sampleLimit);
        setHints(response?.hints || {});
      } catch (error) {
        toast.error('Öğrenme ipuçları getirilemedi: ' + (error.response?.data?.detail || error.message));
        setHints({});
      } finally {
        setLoadingHints(false);
      }
    };

    loadHints();
  }, [selectedTemplateId, sampleLimit]);

  useEffect(() => {
    if (!selectedFieldId) {
      setHistory([]);
      return;
    }

    const parsedFieldId = Number(selectedFieldId);
    if (!Number.isFinite(parsedFieldId)) {
      setHistory([]);
      return;
    }

    const loadHistory = async () => {
      setLoadingHistory(true);
      try {
        const data = await fetchCorrectionHistory({ templateFieldId: parsedFieldId });
        setHistory(Array.isArray(data) ? data : []);
      } catch (error) {
        toast.error('Düzeltme geçmişi getirilemedi: ' + (error.response?.data?.detail || error.message));
        setHistory([]);
      } finally {
        setLoadingHistory(false);
      }
    };

    loadHistory();
  }, [selectedFieldId]);

  const selectedTemplate = useMemo(
    () => templates.find((template) => String(template.id) === String(selectedTemplateId)),
    [templates, selectedTemplateId]
  );

  const selectedDocument = useMemo(() => {
    const parsedId = Number(formState.documentId);
    if (!Number.isFinite(parsedId)) {
      return undefined;
    }

    return documentOptions.find((document) => Number(document.id) === parsedId);
  }, [documentOptions, formState.documentId]);

  const handleTemplateChange = (event) => {
    const value = event.target.value;
    setSelectedTemplateId(value);
    updateFieldSelection('');
    setDocumentOptions([]);
    setDocumentError('');
    setFormState((prev) => ({
      ...prev,
      documentId: '',
      templateFieldId: '',
    }));
  };

  const handleFieldChange = (event) => {
    const value = event.target.value;
    updateFieldSelection(value);
  };

  const handleDocumentChange = (event) => {
    const value = event.target.value;
    setFormState((prev) => ({ ...prev, documentId: value }));
  };

  const handleFormChange = (event) => {
    const { name, value } = event.target;
    setFormState((prev) => ({ ...prev, [name]: value }));
  };

  const handleSubmit = async (event) => {
    event.preventDefault();

    if (!formState.documentId || !formState.correctedValue) {
      toast.error('Belge ID ve düzeltme değeri zorunludur.');
      return;
    }

    if (!selectedTemplateId) {
      toast.error('Lütfen bir şablon seçin.');
      return;
    }

    const parsedDocumentId = Number(formState.documentId);
    if (!Number.isFinite(parsedDocumentId)) {
      toast.error('Belge ID geçerli bir sayı olmalıdır.');
      return;
    }

    let contextPayload = undefined;
    if (formState.context) {
      try {
        contextPayload = JSON.parse(formState.context);
      } catch (error) {
        toast.error('Bağlam bilgisi geçerli JSON formatında olmalıdır.');
        return;
      }
    }

    setSubmitting(true);
    try {
      const parsedTemplateFieldId = Number(formState.templateFieldId);
      const templateFieldIdValue = Number.isFinite(parsedTemplateFieldId)
        ? parsedTemplateFieldId
        : undefined;

      await submitLearningCorrection({
        documentId: parsedDocumentId,
        templateFieldId: templateFieldIdValue,
        originalValue: formState.originalValue || undefined,
        correctedValue: formState.correctedValue,
        context: contextPayload,
        userId: formState.userId ? Number(formState.userId) : undefined,
      });
      toast.success('Düzeltme kaydedildi.');
      setFormState((prev) => ({
        ...initialFormState,
        templateFieldId: templateFieldIdValue !== undefined ? String(templateFieldIdValue) : '',
      }));
      setSelectedFieldId(templateFieldIdValue !== undefined ? String(templateFieldIdValue) : '');
      await Promise.all([
        fetchLearnedHints(Number(selectedTemplateId), sampleLimit).then((response) => {
          setHints(response?.hints || {});
        }),
        templateFieldIdValue !== undefined
          ? fetchCorrectionHistory({ templateFieldId: templateFieldIdValue }).then((data) => {
              setHistory(Array.isArray(data) ? data : []);
            })
          : Promise.resolve(),
      ]);
    } catch (error) {
      toast.error('Düzeltme kaydedilemedi: ' + (error.response?.data?.detail || error.message));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="max-w-6xl mx-auto p-6 space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-gray-800">Şablon Öğrenmesi</h1>
          <p className="text-gray-600">Kullanıcı düzeltmelerini kaydedin ve öğrenilmiş ipuçlarını inceleyin.</p>
        </div>
        {onBack && (
          <button onClick={onBack} className="btn btn-secondary">Ana Sayfaya Dön</button>
        )}
      </div>

      <div className="card">
        <h2 className="text-xl font-semibold mb-4">Şablon Seçimi</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="label" htmlFor="template-select">
              Şablon
            </label>
            <select
              id="template-select"
              value={selectedTemplateId}
              onChange={handleTemplateChange}
              className="input"
            >
              <option value="">Bir şablon seçin</option>
              {templates.map((template) => (
                <option key={template.id} value={template.id}>
                  {template.name} (v{template.version})
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="label" htmlFor="sample-limit">
              Analiz edilecek düzeltme örnekleri
            </label>
            <input
              id="sample-limit"
              type="number"
              min="1"
              max="500"
              value={sampleLimit}
              onChange={(event) => setSampleLimit(Number(event.target.value) || 1)}
              className="input"
            />
          </div>
        </div>

        {loadingTemplate && <p className="text-sm text-gray-500 mt-4">Şablon detayları yükleniyor...</p>}
      </div>

      <div className="card">
        <h2 className="text-xl font-semibold mb-4">Kullanıcı Düzeltmesi Kaydet</h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="label" htmlFor="documentId">
                Belge ID
              </label>
              <input
                id="documentId"
                name="documentId"
                value={formState.documentId}
                onChange={handleDocumentChange}
                className="input"
                placeholder="Belge ID girin veya arayın"
                list="documentId-options"
              />
              <datalist id="documentId-options">
                {documentOptions.map((document) => (
                  <option
                    key={document.id}
                    value={document.id}
                    label={`#${document.id} • ${document.filename} (${document.status})`}
                  />
                ))}
              </datalist>
              {loadingDocuments && (
                <p className="text-sm text-gray-500 mt-2">Belgeler yükleniyor...</p>
              )}
              {documentError && (
                <p className="text-sm text-red-600 mt-2">{documentError}</p>
              )}
              {!loadingDocuments && !documentError && selectedTemplateId &&
                documentOptions.length === 0 && (
                  <p className="text-sm text-gray-500 mt-2">
                    Bu şablon için kayıtlı belge bulunamadı. ID'yi manuel girebilirsiniz.
                  </p>
                )}
              {selectedDocument && (
                <p className="text-sm text-gray-600 mt-2">
                  Seçilen belge: <span className="font-medium">#{selectedDocument.id}</span> •{' '}
                  {selectedDocument.filename} ({selectedDocument.status})
                </p>
              )}
            </div>

            <div>
              <label className="label" htmlFor="templateFieldId">
                Şablon Alanı (opsiyonel)
              </label>
              <select
                id="templateFieldId"
                name="templateFieldId"
                value={formState.templateFieldId}
                onChange={handleFieldChange}
                className="input"
                disabled={!selectedTemplateId || templateFields.length === 0}
              >
                <option value="">Alan seçin</option>
                {templateFields.map((field) => (
                  <option key={field.id} value={field.id}>
                    {field.display_name || field.field_name}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="label" htmlFor="originalValue">
                Orijinal Değer
              </label>
              <input
                id="originalValue"
                name="originalValue"
                value={formState.originalValue}
                onChange={handleFormChange}
                className="input"
                placeholder="Sistemin önerdiği değer"
              />
            </div>

            <div>
              <label className="label" htmlFor="correctedValue">
                Doğru Değer
              </label>
              <input
                id="correctedValue"
                name="correctedValue"
                value={formState.correctedValue}
                onChange={handleFormChange}
                className="input"
                placeholder="Kullanıcı tarafından onaylanan değer"
              />
            </div>

            <div>
              <label className="label" htmlFor="userId">
                Kullanıcı ID (opsiyonel)
              </label>
              <input
                id="userId"
                name="userId"
                value={formState.userId}
                onChange={handleFormChange}
                className="input"
                placeholder="Örn. 7"
              />
            </div>

            <div>
              <label className="label" htmlFor="context">
                Bağlam Bilgisi (JSON)
              </label>
              <textarea
                id="context"
                name="context"
                value={formState.context}
                onChange={handleFormChange}
                className="input h-32"
                placeholder='{"reason": "manual_review"}'
              />
            </div>
          </div>

          <button type="submit" className="btn btn-primary" disabled={submitting}>
            {submitting ? 'Kaydediliyor...' : 'Düzeltmeyi Kaydet'}
          </button>
        </form>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="card">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-xl font-semibold">Öğrenilen İpuçları</h2>
            {loadingHints && <span className="text-sm text-gray-500">Yükleniyor...</span>}
          </div>

          {!selectedTemplateId ? (
            <p className="text-gray-500">İpuçlarını görmek için bir şablon seçin.</p>
          ) : Object.keys(hints).length === 0 ? (
            <p className="text-gray-500">Bu şablon için henüz öğrenilmiş ipucu bulunmuyor.</p>
          ) : (
            <div className="space-y-4">
              {Object.entries(hints).map(([fieldId, hint]) => {
                const field = templateFields.find((item) => String(item.id) === fieldId);
                return (
                  <div key={fieldId} className="border rounded-lg p-4 bg-gray-50">
                    <h3 className="font-semibold text-lg">
                      {field?.display_name || field?.field_name || `Alan #${fieldId}`}
                    </h3>
                    <p className="text-sm text-gray-500 mb-2">Kaynak: {hint.source || 'auto-learning'}</p>
                    {hint.type_hint && (
                      <p className="text-sm text-gray-700">
                        Tahmini veri tipi: <span className="font-medium">{hint.type_hint}</span>
                      </p>
                    )}
                    {Array.isArray(hint.examples) && hint.examples.length > 0 && (
                      <div className="mt-2">
                        <p className="text-sm text-gray-600 mb-1">Örnek değerler:</p>
                        <ul className="list-disc list-inside text-sm text-gray-700 space-y-1">
                          {hint.examples.map((example) => (
                            <li key={example}>{example}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                    {Array.isArray(hint.regex_patterns) && hint.regex_patterns.length > 0 && (
                      <div className="mt-2">
                        <p className="text-sm text-gray-600 mb-1">Önerilen desenler:</p>
                        <ul className="list-disc list-inside text-sm text-gray-700 space-y-1">
                          {hint.regex_patterns.map((pattern) => (
                            <li key={pattern.pattern}>{pattern.pattern}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>

        <div className="card">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-xl font-semibold">Düzeltme Geçmişi</h2>
            {loadingHistory && <span className="text-sm text-gray-500">Yükleniyor...</span>}
          </div>

          {!selectedFieldId ? (
            <p className="text-gray-500">Geçmişi görmek için bir alan seçin.</p>
          ) : history.length === 0 ? (
            <p className="text-gray-500">Bu alan için henüz düzeltme kaydı bulunmuyor.</p>
          ) : (
            <div className="space-y-3 max-h-96 overflow-y-auto">
              {history.map((entry) => (
                <div key={entry.id} className="border rounded p-3 bg-gray-50">
                  <div className="flex items-center justify-between text-sm text-gray-600">
                    <span>Belge #{entry.document_id}</span>
                    <span>{new Date(entry.created_at).toLocaleString('tr-TR')}</span>
                  </div>
                  <p className="text-sm text-gray-600 mt-2">
                    <span className="font-medium text-gray-700">Orijinal:</span> {entry.original_value || '-'}
                  </p>
                  <p className="text-sm text-gray-700">
                    <span className="font-medium text-gray-700">Doğru:</span> {entry.corrected_value}
                  </p>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {selectedTemplate && (
        <div className="card">
          <h2 className="text-xl font-semibold mb-2">Seçili Şablon</h2>
          <p className="text-gray-600">
            <span className="font-medium">{selectedTemplate.name}</span> • Versiyon {selectedTemplate.version}
          </p>
          {selectedTemplate.description && (
            <p className="text-sm text-gray-500 mt-2">{selectedTemplate.description}</p>
          )}
        </div>
      )}
    </div>
  );
};

export default TemplateLearningView;
