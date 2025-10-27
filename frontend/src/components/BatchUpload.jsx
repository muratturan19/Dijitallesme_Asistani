import React, { useState, useEffect } from 'react';
import { useDropzone } from 'react-dropzone';
import { toast } from 'react-toastify';
import { uploadBatchFiles, startBatchProcessing, getBatchStatus, exportBatchResults } from '../api';

const BatchUpload = ({ templateId, onComplete }) => {
  const [files, setFiles] = useState([]);
  const [batchJobId, setBatchJobId] = useState(null);
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setFiles([]);
    setBatchJobId(null);
    setStatus(null);
  }, [templateId]);

  const onDrop = (acceptedFiles) => {
    setFiles([...files, ...acceptedFiles]);
    toast.success(`${acceptedFiles.length} dosya eklendi`);
  };

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'application/pdf': ['.pdf'],
      'image/*': ['.jpg', '.jpeg', '.png'],
    },
    maxFiles: 100,
  });

  const handleUploadAndProcess = async () => {
    if (files.length === 0) {
      toast.error('Lütfen en az bir dosya ekleyin');
      return;
    }

    setLoading(true);

    try {
      // Upload files
      await uploadBatchFiles(files, templateId);

      // Start batch processing
      const result = await startBatchProcessing(templateId);
      setBatchJobId(result.batch_job_id);
      toast.success('Toplu işlem başlatıldı!');
    } catch (error) {
      toast.error('Hata: ' + (error.response?.data?.detail || error.message));
    } finally {
      setLoading(false);
    }
  };

  const removeFile = (index) => {
    setFiles(files.filter((_, i) => i !== index));
  };

  // Poll batch status
  useEffect(() => {
    if (!batchJobId) return;

    const interval = setInterval(async () => {
      try {
        const statusData = await getBatchStatus(batchJobId);
        setStatus(statusData);

        if (statusData.status === 'completed') {
          clearInterval(interval);
          toast.success('Toplu işlem tamamlandı!');
        }
      } catch (error) {
        console.error('Status poll error:', error);
      }
    }, 2000);

    return () => clearInterval(interval);
  }, [batchJobId]);

  const handleDownload = () => {
    window.open(exportBatchResults(batchJobId), '_blank');
  };

  if (batchJobId && status) {
    return (
      <div className="max-w-4xl mx-auto p-6">
        <h1 className="text-3xl font-bold text-gray-800 mb-6">Toplu İşlem Durumu</h1>

        <div className="card mb-6">
          <h3 className="font-semibold mb-4">İlerleme</h3>

          <div className="mb-4">
            <div className="flex justify-between text-sm mb-2">
              <span>Tamamlanan</span>
              <span>{status.progress.toFixed(1)}%</span>
            </div>
            <div className="w-full bg-gray-200 rounded-full h-4">
              <div
                className="bg-primary-600 h-4 rounded-full transition-all"
                style={{ width: `${status.progress}%` }}
              ></div>
            </div>
          </div>

          <div className="grid grid-cols-3 gap-4">
            <div className="bg-gray-50 p-4 rounded">
              <p className="text-sm text-gray-600">Toplam Dosya</p>
              <p className="text-2xl font-bold">{status.total_files}</p>
            </div>
            <div className="bg-green-50 p-4 rounded">
              <p className="text-sm text-gray-600">İşlenen</p>
              <p className="text-2xl font-bold text-green-600">{status.processed_files}</p>
            </div>
            <div className="bg-red-50 p-4 rounded">
              <p className="text-sm text-gray-600">Başarısız</p>
              <p className="text-2xl font-bold text-red-600">{status.failed_files}</p>
            </div>
          </div>

          {status.low_confidence_items && status.low_confidence_items.length > 0 && (
            <div className="mt-4 bg-yellow-50 border border-yellow-200 rounded p-4">
              <p className="text-yellow-800 font-medium">
                ⚠ {status.low_confidence_items.length} belge düşük güven skoruna sahip ve inceleme gerektiriyor
              </p>
            </div>
          )}
        </div>

        {status.status === 'completed' && (
          <div className="flex gap-3">
            <button onClick={() => onComplete()} className="btn btn-secondary flex-1">
              Ana Sayfa
            </button>
            <button onClick={handleDownload} className="btn btn-success flex-1">
              Excel İndir
            </button>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto p-6">
      <h1 className="text-3xl font-bold text-gray-800 mb-2">Toplu Belge İşleme</h1>
      <p className="text-gray-600 mb-6">Birden fazla belgeyi aynı anda işleyin</p>

      <div className="card mb-6">
        <div
          {...getRootProps()}
          className={`dropzone ${isDragActive ? 'dropzone-active' : ''}`}
        >
          <input {...getInputProps()} />
          <p className="text-gray-600">Belgeleri buraya sürükleyin veya tıklayın</p>
          <p className="text-sm text-gray-400 mt-2">PDF, JPG, PNG (Maksimum 100 dosya)</p>
        </div>
      </div>

      {files.length > 0 && (
        <div className="card mb-6">
          <h3 className="font-semibold mb-4">Yüklenen Dosyalar ({files.length})</h3>
          <div className="max-h-64 overflow-y-auto">
            {files.map((file, index) => (
              <div key={index} className="flex items-center justify-between py-2 border-b">
                <div>
                  <p className="font-medium">{file.name}</p>
                  <p className="text-sm text-gray-500">{(file.size / 1024).toFixed(2)} KB</p>
                </div>
                <button
                  onClick={() => removeFile(index)}
                  className="text-red-600 hover:text-red-800"
                >
                  Kaldır
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      <button
        onClick={handleUploadAndProcess}
        className="btn btn-primary w-full"
        disabled={loading || files.length === 0}
      >
        {loading ? 'İşleniyor...' : `${files.length} Dosyayı İşle`}
      </button>
    </div>
  );
};

export default BatchUpload;
