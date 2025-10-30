import React, { useEffect, useMemo, useState } from 'react';
import { toast } from 'react-toastify';
import { updateTemplateFieldMetadata } from '../api';

const extractFieldGuidance = (field) => {
  if (!field || typeof field !== 'object') {
    return '';
  }

  const metadata = field.metadata;
  if (!metadata || typeof metadata !== 'object') {
    return '';
  }

  const candidateKeys = ['llm_guidance', 'llmGuidance', 'llm_instruction', 'guidance'];

  for (const key of candidateKeys) {
    if (metadata[key] !== undefined && metadata[key] !== null) {
      return String(metadata[key]);
    }
  }

  return '';
};

const sanitizeMetadata = (metadata) => {
  if (!metadata || typeof metadata !== 'object') {
    return {};
  }

  return Object.entries(metadata).reduce((accumulator, [key, value]) => {
    if (value !== undefined) {
      accumulator[key] = value;
    }
    return accumulator;
  }, {});
};

const FieldGuidanceEditor = ({ templateId, field, onMetadataUpdated }) => {
  const [guidanceText, setGuidanceText] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setGuidanceText(extractFieldGuidance(field));
  }, [field]);

  const fieldId = useMemo(() => {
    if (!field) {
      return undefined;
    }

    const parsed = Number(field.id);
    return Number.isFinite(parsed) ? parsed : undefined;
  }, [field]);

  const handleSave = async () => {
    if (!Number.isFinite(templateId)) {
      toast.error('Geçersiz şablon kimliği.');
      return;
    }

    if (fieldId === undefined) {
      toast.error('Talimat kaydedilecek alan bulunamadı.');
      return;
    }

    const trimmed = guidanceText.trim();

    const currentMetadata =
      field && typeof field.metadata === 'object' && field.metadata !== null
        ? { ...field.metadata }
        : {};

    if (trimmed) {
      currentMetadata.llm_guidance = trimmed;
    } else {
      delete currentMetadata.llm_guidance;
    }

    const payload = sanitizeMetadata(currentMetadata);

    setSaving(true);
    try {
      const response = await updateTemplateFieldMetadata(templateId, fieldId, payload);
      const nextMetadata =
        response && typeof response.metadata === 'object' && response.metadata !== null
          ? response.metadata
          : {};

      if (typeof onMetadataUpdated === 'function') {
        onMetadataUpdated(fieldId, nextMetadata);
      }

      setGuidanceText(extractFieldGuidance({ metadata: nextMetadata }));
      toast.success('LLM talimatı kaydedildi.');
    } catch (error) {
      toast.error('Talimat kaydedilemedi: ' + (error.response?.data?.detail || error.message));
    } finally {
      setSaving(false);
    }
  };

  if (!field || fieldId === undefined) {
    return null;
  }

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-xl font-semibold">LLM Talimatı</h2>
          <p className="text-sm text-gray-500">
            Seçili alan için yapay zekâya özel talimatlar ekleyin veya güncelleyin.
          </p>
        </div>
        <span className="text-sm text-gray-500">
          Alan: {field.display_name || field.field_name || `#${fieldId}`}
        </span>
      </div>
      <textarea
        id="llm-guidance"
        className="input h-40"
        placeholder="Alan için LLM talimatlarını buraya yazın"
        value={guidanceText}
        onChange={(event) => setGuidanceText(event.target.value)}
      />
      <div className="flex justify-end mt-3">
        <button
          type="button"
          className="btn btn-secondary"
          onClick={handleSave}
          disabled={saving}
        >
          {saving ? 'Kaydediliyor...' : 'Talimatı Kaydet'}
        </button>
      </div>
    </div>
  );
};

export default FieldGuidanceEditor;
