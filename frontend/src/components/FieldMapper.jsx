import React, { useState } from 'react';
import { toast } from 'react-toastify';
import { saveTemplate } from '../api';

const FieldMapper = ({ data, onNext, onBack }) => {
  const [templateName, setTemplateName] = useState('Yeni Şablon');
  const [mappings, setMappings] = useState(data.analysisResult.suggested_mapping);
  const [loading, setLoading] = useState(false);

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

    try {
      await saveTemplate(data.templateId, templateName, mappings);
      toast.success('Şablon kaydedildi!');
      onNext({ ...data, templateName, confirmedMapping: mappings });
    } catch (error) {
      toast.error('Kaydetme hatası: ' + (error.response?.data?.detail || error.message));
    } finally {
      setLoading(false);
    }
  };

  const needsReview = Object.values(mappings).some(m => m.status === 'low');

  return (
    <div className="max-w-6xl mx-auto p-6">
      <h1 className="text-3xl font-bold text-gray-800 mb-2">Alan Eşleştirme</h1>
      <p className="text-gray-600 mb-6">AI tarafından çıkarılan verileri kontrol edin ve düzeltin</p>

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
                <th className="text-left py-3 px-4">Çıkarılan Değer</th>
                <th className="text-left py-3 px-4">Güven Skoru</th>
                <th className="text-left py-3 px-4">Durum</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(mappings).map(([fieldName, fieldData]) => (
                <tr key={fieldName} className="border-b hover:bg-gray-50">
                  <td className="py-3 px-4 font-medium">{fieldName}</td>
                  <td className="py-3 px-4">
                    <input
                      type="text"
                      value={fieldData.value || ''}
                      onChange={(e) => handleValueChange(fieldName, e.target.value)}
                      className="input text-sm"
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
                data.analysisResult.overall_confidence >= 0.8
                  ? 'bg-green-500'
                  : data.analysisResult.overall_confidence >= 0.5
                  ? 'bg-yellow-500'
                  : 'bg-red-500'
              }`}
              style={{ width: `${data.analysisResult.overall_confidence * 100}%` }}
            ></div>
          </div>
          <span className="text-xl font-bold">
            {(data.analysisResult.overall_confidence * 100).toFixed(1)}%
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
