import axios from 'axios';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

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

export const saveTemplate = async (templateId, name, confirmedMapping) => {
  const response = await api.post('/api/template/save', {
    template_id: templateId,
    name,
    confirmed_mapping: confirmedMapping,
  });

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
    target_fields: targetFields,
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
