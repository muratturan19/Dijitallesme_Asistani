import axios from 'axios';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

const normalizeOcrPsm = (value) => {
  if (value === undefined || value === null) {
    return null;
  }

  if (typeof value === 'string') {
    const trimmed = value.trim();
    if (!trimmed || trimmed.toLowerCase() === 'null' || trimmed.toLowerCase() === 'none') {
      return null;
    }

    const numeric = Number(trimmed);
    return Number.isFinite(numeric) ? numeric : null;
  }

  return Number.isFinite(value) ? value : null;
};

const normalizeOcrRoi = (value) => {
  if (value === undefined || value === null) {
    return null;
  }

  if (typeof value === 'string') {
    const trimmed = value.trim();
    if (!trimmed || trimmed.toLowerCase() === 'null' || trimmed.toLowerCase() === 'none') {
      return null;
    }

    return trimmed;
  }

  return value;
};

const normalizeProcessingMode = (value) => {
  if (typeof value === 'string') {
    const normalized = value.trim().toLowerCase();
    return normalized || 'auto';
  }

  if (value === undefined || value === null) {
    return 'auto';
  }

  return String(value).trim().toLowerCase() || 'auto';
};

const normalizeLlmTier = (value) => {
  if (typeof value === 'string') {
    const normalized = value.trim().toLowerCase();
    return normalized || 'standard';
  }

  if (value === undefined || value === null) {
    return 'standard';
  }

  return String(value).trim().toLowerCase() || 'standard';
};

const normalizeHandwritingThreshold = (value) => {
  if (value === undefined || value === null || value === '') {
    return null;
  }

  const numeric = Number(value);

  if (!Number.isFinite(numeric)) {
    return null;
  }

  if (numeric < 0) {
    return 0;
  }

  if (numeric > 1) {
    return 1;
  }

  return Number(numeric.toFixed(3));
};

const normalizeAutoDetectedHandwriting = (value) => {
  if (typeof value === 'boolean') {
    return value;
  }

  if (typeof value === 'string') {
    const normalized = value.trim().toLowerCase();
    if (['true', '1', 'yes', 'on'].includes(normalized)) {
      return true;
    }
    if (['false', '0', 'no', 'off'].includes(normalized)) {
      return false;
    }
  }

  return Boolean(value);
};

const prepareTargetFields = (fields) => {
  if (!Array.isArray(fields)) {
    return fields;
  }

  return fields.map((field) => {
    if (typeof field !== 'object' || field === null) {
      return field;
    }

    return {
      ...field,
      ocr_psm: normalizeOcrPsm(field.ocr_psm),
      ocr_roi: normalizeOcrRoi(field.ocr_roi),
      processing_mode: normalizeProcessingMode(field.processing_mode),
      llm_tier: normalizeLlmTier(field.llm_tier),
      handwriting_threshold: normalizeHandwritingThreshold(field.handwriting_threshold),
      auto_detected_handwriting: normalizeAutoDetectedHandwriting(field.auto_detected_handwriting),
    };
  });
};

// Upload API
export const uploadSampleDocument = async (file) => {
  const formData = new FormData();
  formData.append('file', file);

  const response = await api.post('/api/upload/sample', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  });

  return response.data;
};

export const uploadTemplateFile = async (file) => {
  const formData = new FormData();
  formData.append('file', file);

  const response = await api.post('/api/upload/template', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  });

  return response.data;
};

export const uploadBatchFiles = async (files, templateId) => {
  const formData = new FormData();
  files.forEach(file => {
    formData.append('files', file);
  });

  if (templateId) {
    formData.append('template_id', templateId);
  }

  const response = await api.post('/api/upload/batch', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  });

  return response.data;
};

// Template API
export const analyzeDocument = async (documentId, templateId) => {
  const response = await api.post('/api/template/analyze', {
    document_id: documentId,
    template_id: templateId,
  });

  return response.data;
};

export const saveTemplate = async (templateId, name, confirmedMapping, targetFields) => {
  const response = await api.post('/api/template/save', {
    template_id: templateId,
    name,
    confirmed_mapping: confirmedMapping,
    target_fields: prepareTargetFields(targetFields),
  });

  return response.data;
};

export const updateTemplateFields = async (templateId, targetFields, name) => {
  const payload = {
    target_fields: prepareTargetFields(targetFields),
  };

  if (name && name.trim()) {
    payload.name = name.trim();
  }

  const response = await api.put(`/api/template/${templateId}/fields`, payload);

  return response.data;
};

export const testTemplate = async (documentId, templateId) => {
  const response = await api.post('/api/template/test', null, {
    params: {
      document_id: documentId,
      template_id: templateId,
    },
  });

  return response.data;
};

export const createTemplate = async (name, targetFields, extractionRules) => {
  const response = await api.post('/api/template/create', {
    name,
    target_fields: prepareTargetFields(targetFields),
    extraction_rules: extractionRules,
  });

  return response.data;
};

export const getTemplates = async () => {
  const response = await api.get('/api/template/list');
  return response.data;
};

export const getTemplate = async (templateId) => {
  const response = await api.get(`/api/template/${templateId}`);
  return response.data;
};

export const deleteTemplate = async (templateId) => {
  const response = await api.delete(`/api/template/${templateId}`);
  return response.data;
};

export const getTemplateStats = async (templateId) => {
  const response = await api.get(`/api/template/${templateId}/stats`);
  return response.data;
};

// Batch API
export const startBatchProcessing = async (templateId) => {
  const response = await api.post('/api/batch/start', {
    template_id: templateId,
  });

  return response.data;
};

export const getBatchStatus = async (batchJobId) => {
  const response = await api.get(`/api/batch/status/${batchJobId}`);
  return response.data;
};

export const getBatchJobs = async () => {
  const response = await api.get('/api/batch/list');
  return response.data;
};

export const deleteBatchJob = async (batchJobId) => {
  const response = await api.delete(`/api/batch/${batchJobId}`);
  return response.data;
};

// Export API
export const exportBatchResults = (batchJobId) => {
  return `${API_BASE_URL}/api/export/batch/${batchJobId}`;
};

export const exportValidationReport = (batchJobId) => {
  return `${API_BASE_URL}/api/export/validation/${batchJobId}`;
};

export const exportTemplate = (templateId) => {
  return `${API_BASE_URL}/api/export/template/${templateId}`;
};

export const exportDocument = (documentId) => {
  return `${API_BASE_URL}/api/export/document/${documentId}`;
};

export default api;
