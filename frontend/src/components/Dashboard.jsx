import React, { useState, useEffect } from 'react';
import { toast } from 'react-toastify';
import { getTemplates, deleteTemplate, getBatchJobs } from '../api';

const Dashboard = ({ onNewTemplate, onSelectTemplate }) => {
  const [templates, setTemplates] = useState([]);
  const [batchJobs, setBatchJobs] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    setLoading(true);
    try {
      const [templatesData, jobsData] = await Promise.all([
        getTemplates(),
        getBatchJobs(),
      ]);
      setTemplates(templatesData);
      setBatchJobs(jobsData);
    } catch (error) {
      toast.error('Veri yükleme hatası: ' + (error.response?.data?.detail || error.message));
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteTemplate = async (templateId) => {
    if (!window.confirm('Bu şablonu silmek istediğinizden emin misiniz?')) {
      return;
    }

    try {
      await deleteTemplate(templateId);
      toast.success('Şablon silindi');
      loadData();
    } catch (error) {
      toast.error('Silme hatası: ' + (error.response?.data?.detail || error.message));
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="spinner"></div>
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto p-6">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-3xl font-bold text-gray-800">Dijitalleşme Asistanı</h1>
          <p className="text-gray-600">Şablonlarınızı yönetin ve yeni belgeler işleyin</p>
        </div>
        <button onClick={onNewTemplate} className="btn btn-primary">
          + Yeni Şablon Oluştur
        </button>
      </div>

      {/* Statistics */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
        <div className="card">
          <h3 className="text-sm text-gray-600 mb-2">Toplam Şablon</h3>
          <p className="text-3xl font-bold text-primary-600">{templates.length}</p>
        </div>
        <div className="card">
          <h3 className="text-sm text-gray-600 mb-2">Toplu İşlem</h3>
          <p className="text-3xl font-bold text-primary-600">{batchJobs.length}</p>
        </div>
        <div className="card">
          <h3 className="text-sm text-gray-600 mb-2">Başarı Oranı</h3>
          <p className="text-3xl font-bold text-green-600">
            {batchJobs.length > 0
              ? (
                  (batchJobs.reduce((acc, job) => acc + job.processed_files, 0) /
                    batchJobs.reduce((acc, job) => acc + job.total_files, 0)) *
                  100
                ).toFixed(1)
              : 0}
            %
          </p>
        </div>
      </div>

      {/* Templates */}
      <div className="card mb-8">
        <h2 className="text-2xl font-semibold mb-4">Şablonlar</h2>

        {templates.length === 0 ? (
          <div className="text-center py-8 text-gray-500">
            <p>Henüz şablon oluşturulmamış</p>
            <button onClick={onNewTemplate} className="btn btn-primary mt-4">
              İlk Şablonunuzu Oluşturun
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {templates.map((template) => (
              <div key={template.id} className="border rounded-lg p-4 hover:shadow-md transition-shadow">
                <div className="flex items-start justify-between mb-2">
                  <div>
                    <h3 className="font-semibold text-lg">{template.name}</h3>
                    <p className="text-sm text-gray-500">Versiyon {template.version}</p>
                  </div>
                  <button
                    onClick={() => handleDeleteTemplate(template.id)}
                    className="text-red-600 hover:text-red-800 text-sm"
                  >
                    Sil
                  </button>
                </div>

                <div className="mb-3">
                  <p className="text-sm text-gray-600">
                    {template.target_fields.length} alan
                  </p>
                  <p className="text-xs text-gray-400">
                    Oluşturulma: {new Date(template.created_at).toLocaleDateString('tr-TR')}
                  </p>
                </div>

                <button
                  onClick={() => onSelectTemplate(template)}
                  className="btn btn-primary w-full text-sm"
                >
                  Bu Şablonu Kullan
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Recent Batch Jobs */}
      {batchJobs.length > 0 && (
        <div className="card">
          <h2 className="text-2xl font-semibold mb-4">Son Toplu İşlemler</h2>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b">
                  <th className="text-left py-3 px-4">ID</th>
                  <th className="text-left py-3 px-4">Durum</th>
                  <th className="text-left py-3 px-4">Dosya Sayısı</th>
                  <th className="text-left py-3 px-4">İşlenen</th>
                  <th className="text-left py-3 px-4">Başarısız</th>
                  <th className="text-left py-3 px-4">Tarih</th>
                </tr>
              </thead>
              <tbody>
                {batchJobs.slice(0, 10).map((job) => (
                  <tr key={job.batch_job_id} className="border-b hover:bg-gray-50">
                    <td className="py-3 px-4">#{job.batch_job_id}</td>
                    <td className="py-3 px-4">
                      <span
                        className={`px-2 py-1 rounded text-sm ${
                          job.status === 'completed'
                            ? 'bg-green-100 text-green-800'
                            : job.status === 'processing'
                            ? 'bg-blue-100 text-blue-800'
                            : 'bg-red-100 text-red-800'
                        }`}
                      >
                        {job.status === 'completed'
                          ? 'Tamamlandı'
                          : job.status === 'processing'
                          ? 'İşleniyor'
                          : 'Başarısız'}
                      </span>
                    </td>
                    <td className="py-3 px-4">{job.total_files}</td>
                    <td className="py-3 px-4 text-green-600">{job.processed_files}</td>
                    <td className="py-3 px-4 text-red-600">{job.failed_files}</td>
                    <td className="py-3 px-4 text-sm text-gray-500">
                      {new Date(job.created_at).toLocaleDateString('tr-TR')}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};

export default Dashboard;
