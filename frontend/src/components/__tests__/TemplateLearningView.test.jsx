import React from 'react';
import { render, screen, waitFor, fireEvent, within } from '@testing-library/react';
import TemplateLearningView from '../TemplateLearningView';

jest.mock('../../api', () => ({
  getTemplates: jest.fn(),
  getTemplate: jest.fn(),
  submitLearningCorrection: jest.fn(),
  fetchLearnedHints: jest.fn(),
  fetchCorrectionHistory: jest.fn(),
}));

jest.mock('react-toastify', () => ({
  toast: {
    error: jest.fn(),
    success: jest.fn(),
  },
}));

const {
  getTemplates,
  getTemplate,
  submitLearningCorrection,
  fetchLearnedHints,
  fetchCorrectionHistory,
} = require('../../api');
const { toast } = require('react-toastify');

describe('TemplateLearningView', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('loads templates and displays hints and history for a selected template', async () => {
    getTemplates.mockResolvedValue([
      { id: 1, name: 'Fatura', version: 3 },
    ]);
    getTemplate.mockResolvedValue({
      id: 1,
      target_fields: [
        { id: 11, field_name: 'total_amount', display_name: 'Toplam Tutar' },
      ],
    });
    fetchLearnedHints.mockResolvedValue({
      template_id: 1,
      hints: {
        11: {
          source: 'auto-learning',
          type_hint: 'number',
          examples: ['100', '250'],
          regex_patterns: [{ pattern: '^\\d+$' }],
        },
      },
    });
    fetchCorrectionHistory.mockResolvedValue([
      {
        id: 5,
        document_id: 42,
        corrected_value: '125',
        original_value: '15',
        created_at: new Date('2024-01-01T12:00:00Z').toISOString(),
      },
    ]);
    submitLearningCorrection.mockResolvedValue({ id: 99 });

    render(<TemplateLearningView />);

    await waitFor(() => expect(getTemplates).toHaveBeenCalled());
    await screen.findByRole('option', { name: /Fatura/ });

    fireEvent.change(screen.getByLabelText('Şablon'), { target: { value: '1' } });

    await waitFor(() => expect(getTemplate).toHaveBeenCalledWith(1));
    await waitFor(() => expect(fetchLearnedHints).toHaveBeenCalledWith(1, 50));

    fireEvent.change(screen.getByLabelText('Şablon Alanı (opsiyonel)'), { target: { value: '11' } });

    await waitFor(() => expect(fetchCorrectionHistory).toHaveBeenCalledWith({ templateFieldId: 11 }));

    expect(await screen.findByText('Örnek değerler:')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Toplam Tutar' })).toBeInTheDocument();
    const historyHeader = await screen.findByText(/Belge #42/);
    const historyCard = historyHeader.closest('div.border');
    expect(historyCard).not.toBeNull();
    expect(within(historyCard).getByText('125')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Belge ID'), { target: { value: '77' } });
    fireEvent.change(screen.getByLabelText('Doğru Değer'), { target: { value: '890' } });

    fireEvent.click(screen.getByText('Düzeltmeyi Kaydet'));

    await waitFor(() => expect(submitLearningCorrection).toHaveBeenCalledWith({
      documentId: 77,
      templateFieldId: 11,
      originalValue: undefined,
      correctedValue: '890',
      context: undefined,
      userId: undefined,
    }));
  });

  it('does not request correction history when the selected field id is not numeric', async () => {
    getTemplates.mockResolvedValue([
      { id: 1, name: 'Fatura', version: 3 },
    ]);
    getTemplate.mockResolvedValue({
      id: 1,
      target_fields: [
        { id: 'foo', field_name: 'unknown_field', display_name: 'Bilinmeyen Alan' },
      ],
    });
    fetchLearnedHints.mockResolvedValue({ template_id: 1, hints: {} });
    fetchCorrectionHistory.mockResolvedValue([]);

    render(<TemplateLearningView />);

    await waitFor(() => expect(getTemplates).toHaveBeenCalled());

    fireEvent.change(screen.getByLabelText('Şablon'), { target: { value: '1' } });

    await waitFor(() => expect(getTemplate).toHaveBeenCalledWith(1));

    const fieldSelect = screen.getByLabelText('Şablon Alanı (opsiyonel)');
    fireEvent.change(fieldSelect, { target: { value: 'foo' } });

    await waitFor(() => {
      expect(fetchCorrectionHistory).not.toHaveBeenCalled();
    });

    expect(toast.error).not.toHaveBeenCalled();
  });
});
