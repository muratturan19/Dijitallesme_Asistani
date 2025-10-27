import React, { useEffect, useMemo, useRef, useState } from 'react';
import { toast } from 'react-toastify';
import { getTemplates, deleteTemplate, getBatchJobs } from '../api';

const Dashboard = ({ onNewTemplate, onSelectTemplate, onResumeBatch, activeSection = 'overview' }) => {
  const [templates, setTemplates] = useState([]);
  const [batchJobs, setBatchJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const pendingSectionRef = useRef(null);

  useEffect(() => {
    loadData();
  }, []);

  useEffect(() => {
    if (activeSection === 'pending' && pendingSectionRef.current) {
      pendingSectionRef.current.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }, [activeSection, batchJobs.length]);

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

  const templatesById = useMemo(() => {
    const map = new Map();
    templates.forEach((template) => {
      map.set(template.id, template);
    });
    return map;
  }, [templates]);

  const pendingJobs = useMemo(
    () => batchJobs.filter((job) => job.status !== 'completed'),
    [batchJobs]
  );

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

      {/* Pending Jobs */}
      <div ref={pendingSectionRef} className={`card mb-8 ${activeSection === 'pending' ? 'ring-2 ring-primary-400' : ''}`}>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-2xl font-semibold">Bekleyen Toplu İşler</h2>
          <button onClick={loadData} className="btn btn-secondary text-sm">Yenile</button>
        </div>

        {pendingJobs.length === 0 ? (
          <p className="text-gray-500">Bekleyen toplu iş bulunmuyor. Yeni belgeler eklemek için bir şablon seçin.</p>
        ) : (
          <div className="space-y-4">
            {pendingJobs.map((job) => {
              const template = templatesById.get(job.template_id);
              const progress = job.total_files
                ? Math.min(100, Math.round((job.processed_files / job.total_files) * 100))
                : 0;

              return (
                <div
                  key={job.batch_job_id}
                  className="border rounded-lg p-4 bg-gray-50 hover:bg-white transition-colors"
                >
                  <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
                    <div>
                      <h3 className="font-semibold text-lg">
                        {template?.name || `Şablon #${job.template_id}`}
                      </h3>
                      <p className="text-sm text-gray-500">
                        İş #{job.batch_job_id} • {new Date(job.created_at).toLocaleString('tr-TR')}
                      </p>
                      <p className="text-sm text-gray-600 mt-1">
                        {job.processed_files}/{job.total_files} belge işlendi
                      </p>
                    </div>

                    <div className="flex-1">
                      <div className="flex items-center justify-between text-xs text-gray-500 mb-1">
                        <span>İlerleme</span>
                        <span>%{progress}</span>
                      </div>
                      <div className="w-full bg-gray-200 rounded-full h-2">
                        <div
                          className="bg-primary-500 h-2 rounded-full"
                          style={{ width: `${progress}%` }}
                        />
                      </div>
                    </div>

                    <div className="flex flex-col gap-2 min-w-[160px]">
                      <span
                        className={`px-2 py-1 text-sm rounded text-center ${
                          job.status === 'processing'
                            ? 'bg-blue-100 text-blue-700'
                            : 'bg-yellow-100 text-yellow-700'
                        }`}
                      >
                        {job.status === 'processing' ? 'İşleniyor' : 'Beklemede'}
                      </span>
                      <button
                        onClick={() => onResumeBatch?.(job.template_id)}
                        className="btn btn-primary text-sm"
                      >
                        Toplu İşe Devam Et
                      </button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
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
