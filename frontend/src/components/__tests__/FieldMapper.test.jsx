import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import FieldMapper from '../FieldMapper';

jest.mock('../../api', () => ({
  saveTemplate: jest.fn(),
  reanalyzeFields: jest.fn(),
}));

jest.mock('react-toastify', () => ({
  toast: {
    error: jest.fn(),
    success: jest.fn(),
    warn: jest.fn(),
  },
}));

const { reanalyzeFields } = require('../../api');
const { toast } = require('react-toastify');

describe('FieldMapper reanalyze flow', () => {
  const baseData = {
    documentId: 5,
    templateId: 9,
    templateFields: [
      { field_name: 'total', data_type: 'number', enabled: true },
    ],
    templateName: 'Test Şablon',
    analysisResult: {
      suggested_mapping: {
        total: {
          value: '100',
          confidence: 0.42,
          status: 'low',
          source: 'llm-primary',
        },
      },
      overall_confidence: 0.42,
      message: 'Analiz tamamlandı',
      extraction_source: 'ocr',
      vision_fallback: null,
      specialist: null,
    },
  };

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('sends selected fields to reanalyze endpoint and updates mappings', async () => {
    reanalyzeFields.mockResolvedValue({
      updated_fields: {
        total: {
          value: '120',
          confidence: 0.91,
          status: 'high',
          source: 'llm-specialist',
        },
      },
      specialist: {
        resolved_fields: ['total'],
        requested_fields: ['total'],
        latency_seconds: 1.23,
      },
      message: '1 alan yeniden analiz edildi.',
    });

    render(<FieldMapper data={baseData} onNext={jest.fn()} onBack={jest.fn()} />);

    const reanalyzeButton = screen.getByRole('button', { name: /Yeniden Analiz Et/i });
    expect(reanalyzeButton).toBeDisabled();

    const reanalyzeCheckbox = screen.getByLabelText('Seç');
    fireEvent.click(reanalyzeCheckbox);

    expect(reanalyzeButton).not.toBeDisabled();

    fireEvent.click(reanalyzeButton);

    await waitFor(() => expect(reanalyzeFields).toHaveBeenCalledTimes(1));

    expect(reanalyzeFields).toHaveBeenCalledWith(
      5,
      9,
      ['total'],
      {
        total: baseData.analysisResult.suggested_mapping.total,
      }
    );

    await screen.findByDisplayValue('120');

    expect(toast.success).toHaveBeenCalledWith('1 alan yeniden analiz edildi.');
  });
});
