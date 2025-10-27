import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import Dashboard from '../Dashboard';

jest.mock('../../api', () => ({
  getTemplates: jest.fn(),
  deleteTemplate: jest.fn(),
  getBatchJobs: jest.fn(),
}));

jest.mock('react-toastify', () => ({
  toast: {
    error: jest.fn(),
    success: jest.fn(),
  },
}));

const { getTemplates, getBatchJobs } = require('../../api');

beforeAll(() => {
  if (!window.HTMLElement.prototype.scrollIntoView) {
    window.HTMLElement.prototype.scrollIntoView = jest.fn();
  }
});

describe('Dashboard', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('renders pending jobs panel and triggers resume callback', async () => {
    getTemplates.mockResolvedValue([
      { id: 1, name: 'Fatura', version: 1, target_fields: [] },
    ]);
    getBatchJobs.mockResolvedValue([
      {
        batch_job_id: 10,
        template_id: 1,
        status: 'processing',
        total_files: 5,
        processed_files: 2,
        failed_files: 0,
        created_at: new Date('2024-01-02T10:00:00Z').toISOString(),
      },
    ]);

    const onResumeBatch = jest.fn();

    render(
      <Dashboard
        onNewTemplate={jest.fn()}
        onSelectTemplate={jest.fn()}
        onResumeBatch={onResumeBatch}
        activeSection="pending"
      />
    );

    await waitFor(() => expect(screen.getByText('Bekleyen Toplu İşler')).toBeInTheDocument());
    const resumeButton = await screen.findByRole('button', { name: 'Toplu İşe Devam Et' });

    fireEvent.click(resumeButton);
    expect(onResumeBatch).toHaveBeenCalledWith(1);
  });
});
