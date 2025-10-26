import React, { useEffect, useMemo, useState } from 'react';
import { toast } from 'react-toastify';
import { saveTemplate } from '../api';

const FieldMapper = ({ data, onNext, onBack }) => {
  const [templateName, setTemplateName] = useState(data.templateName || 'Yeni Şablon');
  const [mappings, setMappings] = useState(() => data.analysisResult?.suggested_mapping || {});
  const [loading, setLoading] = useState(false);
  const analysisError = data.analysisResult?.error;
  const overallConfidence = data.analysisResult?.overall_confidence || 0;
  const [fieldConfigs, setFieldConfigs] = useState(() => {
    if (Array.isArray(data.templateFields) && data.templateFields.length > 0) {
      return data.templateFields.map(field => ({
        ...field,
        enabled: field.enabled !== false,
      }));
    }

    return Object.keys(data.analysisResult?.suggested_mapping || {}).map(fieldName => ({
      field_name: fieldName,
      data_type: 'text',
      required: false,
      regex_hint: '',
      enabled: true,
    }));
  });

  useEffect(() => {
    if (Array.isArray(data.templateFields) && data.templateFields.length > 0) {
      setFieldConfigs(
        data.templateFields.map(field => ({
          ...field,
          enabled: field.enabled !== false,
        }))
      );
    }
  }, [data.templateFields]);

  useEffect(() => {
    if (data.analysisResult?.suggested_mapping) {
      setMappings(data.analysisResult.suggested_mapping);
    }
  }, [data.analysisResult?.suggested_mapping]);

  useEffect(() => {
    if (data.templateName) {
      setTemplateName(data.templateName);
    }
  }, [data.templateName]);

  const activeFieldNames = useMemo(() => {
    return new Set(
      fieldConfigs
        .filter(field => field.enabled !== false)
        .map(field => field.field_name)
    );
  }, [fieldConfigs]);

  const getStatusColor = (status) => {
    switch (status) {
      case 'high':
        return 'bg-green-100 text-green-800';
      case 'medium':
        return 'bg-yellow-100 text-yellow-800';
      case 'low':
        return 'bg-red-100 text-red-800';
      default:
        return 'bg-gray-100 text-gray-800';
    }
  };

  const getStatusIcon = (status) => {
    switch (status) {
      case 'high':
        return '✓';
      case 'medium':
        return '⚠';
      case 'low':
        return '✗';
      default:
        return '?';
    }
  };

  const handleValueChange = (fieldName, newValue) => {
    setMappings({
      ...mappings,
      [fieldName]: {
        ...mappings[fieldName],
        value: newValue,
        confidence: 1.0, // User-corrected values have 100% confidence
        status: 'high',
      },
    });
  };

  const handleSave = async () => {
    setLoading(true);
    const trimmedName = templateName.trim() || 'Yeni Şablon';
    setTemplateName(trimmedName);

    try {
      await saveTemplate(data.templateId, trimmedName, mappings, fieldConfigs);
      toast.success('Şablon kaydedildi!');
      onNext({
        ...data,
        templateName: trimmedName,
        confirmedMapping: mappings,
        templateFields: fieldConfigs,
      });
    } catch (error) {
      toast.error('Kaydetme hatası: ' + (error.response?.data?.detail || error.message));
    } finally {
      setLoading(false);
    }
  };

  const needsReview = Object.entries(mappings).some(
    ([fieldName, fieldData]) => activeFieldNames.has(fieldName) && fieldData.status === 'low'
  );

  const handleFieldConfigChange = (fieldName, key, value) => {
    setFieldConfigs(prev => {
      const exists = prev.some(field => field.field_name === fieldName);

      if (!exists) {
        return [
          ...prev,
          {
            field_name: fieldName,
            data_type: key === 'data_type' ? value : 'text',
            required: key === 'required' ? value : false,
            regex_hint: key === 'regex_hint' ? value : '',
            enabled: key === 'enabled' ? value : true,
          },
        ];
      }

      return prev.map(field =>
        field.field_name === fieldName
          ? {
              ...field,
              [key]: value,
            }
          : field
      );
    });
  };

  useEffect(() => {
    setFieldConfigs(prev => {
      const existingNames = new Set(prev.map(field => field.field_name));
      const additions = Object.keys(mappings || {}).filter(
        fieldName => !existingNames.has(fieldName)
      );

      if (additions.length === 0) {
        return prev;
      }

      const newEntries = additions.map(fieldName => ({
        field_name: fieldName,
        data_type: 'text',
        required: false,
        regex_hint: '',
        enabled: true,
      }));

      return [...prev, ...newEntries];
    });
  }, [mappings]);

  return (
    <div className="max-w-6xl mx-auto p-6">
      <h1 className="text-3xl font-bold text-gray-800 mb-2">Alan Eşleştirme</h1>
      <p className="text-gray-600 mb-6">AI tarafından çıkarılan verileri kontrol edin ve düzeltin</p>

      {analysisError && (
        <div className="mb-6 rounded-lg border border-red-200 bg-red-50 p-4 text-red-700">
          <strong className="block font-semibold mb-1">AI eşleme sırasında hata</strong>
          <span>{analysisError}</span>
        </div>
      )}

      {/* Template Name */}
      <div className="card mb-6">
        <label className="label">Şablon Adı</label>
        <input
          type="text"
          value={templateName}
          onChange={(e) => setTemplateName(e.target.value)}
          className="input"
          placeholder="Şablon için bir isim girin"
        />
      </div>

      {/* OCR Text Preview */}
      <div className="card mb-6">
        <h3 className="font-semibold mb-2">OCR Metni (Önizleme)</h3>
        <div className="bg-gray-50 p-4 rounded max-h-40 overflow-y-auto text-sm">
          {data.analysisResult.ocr_text.substring(0, 500)}...
        </div>
        <p className="text-xs text-gray-500 mt-2">
          Toplam {data.analysisResult.word_count} kelime bulundu
        </p>
      </div>

      {/* Field Mappings */}
      <div className="card mb-6">
        <h3 className="font-semibold mb-4">Çıkarılan Alanlar</h3>

        {needsReview && (
          <div className="bg-yellow-50 border border-yellow-200 rounded p-3 mb-4">
            <p className="text-yellow-800 text-sm">
              ⚠ Bazı alanlar düşük güven skoruna sahip. Lütfen kontrol edin.
            </p>
          </div>
        )}

        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b">
                <th className="text-left py-3 px-4">Hedef Alan</th>
                <th className="text-left py-3 px-4">Alan Ayarları</th>
                <th className="text-left py-3 px-4">Çıkarılan Değer</th>
                <th className="text-left py-3 px-4">Güven Skoru</th>
                <th className="text-left py-3 px-4">Durum</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(mappings).map(([fieldName, fieldData]) => (
                <tr
                  key={fieldName}
                  className={`border-b hover:bg-gray-50 ${
                    activeFieldNames.has(fieldName) ? '' : 'opacity-60'
                  }`}
                >
                  <td className="py-3 px-4 font-medium align-top">{fieldName}</td>
                  <td className="py-3 px-4 text-sm align-top">
                    {(() => {
                      const fieldConfig = fieldConfigs.find(
                        field => field.field_name === fieldName
                      ) || {
                        field_name: fieldName,
                        data_type: 'text',
                        required: false,
                        regex_hint: '',
                        enabled: true,
                      };
                      const isEnabled = fieldConfig.enabled !== false;

                      return (
                        <div className="flex flex-col gap-3">
                          <div className="flex flex-wrap items-center gap-4">
                            <label className="flex items-center gap-2 text-sm">
                              <input
                                type="checkbox"
                                className="rounded"
                                checked={isEnabled}
                                onChange={(e) =>
                                  handleFieldConfigChange(fieldName, 'enabled', e.target.checked)
                                }
                              />
                              <span>Dahil Et</span>
                            </label>
                            <div>
                              <label className="block text-xs text-gray-500 mb-1">Veri Tipi</label>
                              <select
                                className="border rounded px-2 py-1 text-sm"
                                value={fieldConfig.data_type || 'text'}
                                onChange={(e) =>
                                  handleFieldConfigChange(fieldName, 'data_type', e.target.value)
                                }
                              >
                                <option value="text">Metin</option>
                                <option value="number">Sayı</option>
                                <option value="date">Tarih</option>
                              </select>
                            </div>
                            <label className="flex items-center gap-2 text-sm">
                              <input
                                type="checkbox"
                                className="rounded"
                                checked={fieldConfig.required || false}
                                onChange={(e) =>
                                  handleFieldConfigChange(fieldName, 'required', e.target.checked)
                                }
                              />
                              <span>Gerekli</span>
                            </label>
                          </div>
                          <div>
                            <label className="block text-xs text-gray-500 mb-1">Regex İpucu</label>
                            <input
                              type="text"
                              className="input text-sm"
                              value={fieldConfig.regex_hint || ''}
                              onChange={(e) =>
                                handleFieldConfigChange(fieldName, 'regex_hint', e.target.value)
                              }
                              placeholder="Örn: ^[0-9]{11}$"
                            />
                          </div>
                        </div>
                      );
                    })()}
                  </td>
                  <td className="py-3 px-4">
                    <input
                      type="text"
                      value={fieldData.value || ''}
                      onChange={(e) => handleValueChange(fieldName, e.target.value)}
                      className="input text-sm"
                      disabled={!activeFieldNames.has(fieldName)}
                      placeholder="Değer giriniz"
                    />
                    {fieldData.source && (
                      <p className="text-xs text-gray-500 mt-1">{fieldData.source}</p>
                    )}
                  </td>
                  <td className="py-3 px-4">
                    <div className="flex items-center">
                      <div className="w-24 bg-gray-200 rounded-full h-2 mr-2">
                        <div
                          className={`h-2 rounded-full ${
                            fieldData.confidence >= 0.8
                              ? 'bg-green-500'
                              : fieldData.confidence >= 0.5
                              ? 'bg-yellow-500'
                              : 'bg-red-500'
                          }`}
                          style={{ width: `${fieldData.confidence * 100}%` }}
                        ></div>
                      </div>
                      <span className="text-sm">{(fieldData.confidence * 100).toFixed(0)}%</span>
                    </div>
                  </td>
                  <td className="py-3 px-4">
                    <span className={`px-3 py-1 rounded-full text-sm ${getStatusColor(fieldData.status)}`}>
                      {getStatusIcon(fieldData.status)} {fieldData.status === 'high' ? 'Yüksek' : fieldData.status === 'medium' ? 'Orta' : 'Düşük'}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Overall Confidence */}
      <div className="card mb-6">
        <h3 className="font-semibold mb-2">Genel Güven Skoru</h3>
        <div className="flex items-center">
          <div className="flex-1 bg-gray-200 rounded-full h-4 mr-4">
            <div
              className={`h-4 rounded-full ${
                overallConfidence >= 0.8
                  ? 'bg-green-500'
                  : overallConfidence >= 0.5
                  ? 'bg-yellow-500'
                  : 'bg-red-500'
              }`}
              style={{ width: `${overallConfidence * 100}%` }}
            ></div>
          </div>
          <span className="text-xl font-bold">
            {(overallConfidence * 100).toFixed(1)}%
          </span>
        </div>
      </div>

      {/* Actions */}
      <div className="flex gap-3">
        <button onClick={onBack} className="btn btn-secondary flex-1" disabled={loading}>
          Geri
        </button>
        <button onClick={handleSave} className="btn btn-primary flex-1" disabled={loading}>
          {loading ? 'Kaydediliyor...' : 'Şablonu Kaydet'}
        </button>
      </div>
    </div>
  );
};

export default FieldMapper;
