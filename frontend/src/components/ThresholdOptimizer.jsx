import React, { useMemo, useState } from 'react';
import { toast } from 'react-toastify';
import {
  LineChart,
  Line,
  CartesianGrid,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';
import FileUploader from './FileUploader';
import { optimizeThresholds } from '../api';

const defaultIoURange = { min: 0.3, max: 0.7, step: 0.05 };
const defaultConfRange = { min: 0.1, max: 0.5, step: 0.05 };

const formatNumber = (value, fractionDigits = 2) => {
  if (value === undefined || value === null || Number.isNaN(value)) {
    return '-';
  }
  return Number(value).toFixed(fractionDigits);
};

const getHeatmapColor = (value) => {
  const clamped = Math.max(0, Math.min(100, Number(value) || 0));
  const hue = (clamped / 100) * 120; // 0 -> kırmızı, 120 -> yeşil
  const lightness = 70 - (clamped / 100) * 20;
  return `hsl(${hue}, 65%, ${lightness}%)`;
};

const MetricCard = ({ title, value, target, description }) => {
  const numericValue = Number(value) || 0;
  const reachedTarget = numericValue >= target;
  const delta = numericValue - target;
  const arrow = reachedTarget ? '↑' : '↓';
  const progress = Math.max(0, Math.min(100, numericValue));
  const barColor = reachedTarget ? 'bg-green-500' : 'bg-amber-500';

  return (
    <div className="border rounded-xl bg-white shadow-sm p-5 space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-600">{title}</h3>
        <span className={`px-2 py-0.5 text-xs rounded-full ${reachedTarget ? 'bg-green-100 text-green-700' : 'bg-amber-100 text-amber-700'}`}>
          Hedef: %{formatNumber(target)}
        </span>
      </div>
      <p className="text-3xl font-bold text-gray-900">%{formatNumber(value)}</p>
      <div className="w-full bg-gray-200 rounded-full h-2">
        <div className={`${barColor} h-2 rounded-full`} style={{ width: `${progress}%` }} />
      </div>
      <div className="text-sm text-gray-600 flex items-center gap-2">
        <span className={reachedTarget ? 'text-green-600 font-semibold' : 'text-amber-600 font-semibold'}>
          {arrow} {formatNumber(Math.abs(delta))}% {reachedTarget ? 'fazla' : 'eksik'}
        </span>
        <span className="text-gray-400">•</span>
        <span>{description}</span>
      </div>
    </div>
  );
};

const DualRangeInput = ({ label, range, limits, onChange }) => {
  const updateRange = (key, value) => {
    const numeric = Number(value);
    if (Number.isNaN(numeric)) {
      return;
    }
    if (key === 'step' && numeric <= 0) {
      return;
    }
    const updated = { ...range, [key]: numeric };
    if (updated.min >= updated.max) {
      return;
    }
    onChange(updated);
  };

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-gray-700">{label}</span>
        <span className="text-xs text-gray-500">
          {formatNumber(range.min, 2)} - {formatNumber(range.max, 2)} (step {formatNumber(range.step, 2)})
        </span>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
        <label className="text-xs text-gray-500 uppercase tracking-wide">
          Min
          <input
            type="number"
            step="0.01"
            value={range.min}
            min={limits.min}
            max={limits.max}
            onChange={(event) => updateRange('min', event.target.value)}
            className="mt-1 w-full rounded-md border-gray-300 focus:border-primary-500 focus:ring-primary-500 text-sm"
          />
        </label>
        <label className="text-xs text-gray-500 uppercase tracking-wide">
          Max
          <input
            type="number"
            step="0.01"
            value={range.max}
            min={limits.min}
            max={limits.max}
            onChange={(event) => updateRange('max', event.target.value)}
            className="mt-1 w-full rounded-md border-gray-300 focus:border-primary-500 focus:ring-primary-500 text-sm"
          />
        </label>
        <label className="text-xs text-gray-500 uppercase tracking-wide">
          Step
          <input
            type="number"
            step="0.01"
            value={range.step}
            min={0.01}
            max={1}
            onChange={(event) => updateRange('step', event.target.value)}
            className="mt-1 w-full rounded-md border-gray-300 focus:border-primary-500 focus:ring-primary-500 text-sm"
          />
        </label>
      </div>
    </div>
  );
};

const ThresholdOptimizer = () => {
  const [bestModel, setBestModel] = useState(null);
  const [dataConfig, setDataConfig] = useState(null);
  const [iouRange, setIouRange] = useState(defaultIoURange);
  const [confRange, setConfRange] = useState(defaultConfRange);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [activeHeatmapMetric, setActiveHeatmapMetric] = useState('f1');

  const uniqueIoU = useMemo(() => {
    if (!result?.heatmap?.length) {
      return [];
    }
    return Array.from(new Set(result.heatmap.map((item) => Number(item.iou)))).sort((a, b) => a - b);
  }, [result]);

  const uniqueConf = useMemo(() => {
    if (!result?.heatmap?.length) {
      return [];
    }
    return Array.from(new Set(result.heatmap.map((item) => Number(item.confidence)))).sort((a, b) => a - b);
  }, [result]);

  const heatmapMatrix = useMemo(() => {
    if (!result?.heatmap?.length) {
      return new Map();
    }
    const map = new Map();
    result.heatmap.forEach((item) => {
      const key = `${Number(item.iou).toFixed(4)}-${Number(item.confidence).toFixed(4)}`;
      map.set(key, item);
    });
    return map;
  }, [result]);

  const chartData = useMemo(() => {
    if (!result?.training_curves) {
      return [];
    }
    const curves = result.training_curves;
    return curves.epochs.map((epoch, index) => ({
      epoch,
      trainLoss: curves.train_loss[index],
      valLoss: curves.val_loss[index],
      precision: curves.precision[index],
      recall: curves.recall[index],
      map50: curves.map50[index],
      map5095: curves.map5095[index],
    }));
  }, [result]);

  const handleOptimize = async () => {
    if (!bestModel || !dataConfig) {
      toast.warn('Lütfen best.pt ve data.yaml dosyalarını yükleyin.');
      return;
    }

    setLoading(true);
    try {
      const formData = new FormData();
      formData.append('best_model', bestModel);
      formData.append('data_config', dataConfig);
      formData.append('iou_range', JSON.stringify(iouRange));
      formData.append('conf_range', JSON.stringify(confRange));

      const response = await optimizeThresholds(formData);
      setResult(response);
      toast.success('Threshold optimizasyonu tamamlandı.');
    } catch (error) {
      const detail = error.response?.data?.detail || error.message;
      toast.error(`Optimizasyon hatası: ${detail}`);
    } finally {
      setLoading(false);
    }
  };

  const handleDownloadConfig = () => {
    if (!result?.production_config?.content) {
      return;
    }

    const blob = new Blob([result.production_config.content], { type: 'application/x-yaml;charset=utf-8' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = result.production_config.filename || 'production_config.yaml';
    link.click();
    URL.revokeObjectURL(link.href);
  };

  const renderHeatmapCell = (iouValue, confValue) => {
    const key = `${Number(iouValue).toFixed(4)}-${Number(confValue).toFixed(4)}`;
    const item = heatmapMatrix.get(key);
    if (!item) {
      return <td key={confValue} className="p-2 text-center text-sm">-</td>;
    }
    const value = item[activeHeatmapMetric];
    const backgroundColor = getHeatmapColor(value);

    return (
      <td
        key={confValue}
        className="p-2 text-center text-xs font-semibold text-gray-800 rounded"
        style={{ backgroundColor }}
      >
        {formatNumber(value)}
      </td>
    );
  };

  return (
    <div className="max-w-7xl mx-auto px-6 py-8 space-y-8">
      <div className="bg-white shadow rounded-2xl p-6 space-y-6">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div>
            <h1 className="text-3xl font-bold text-gray-900">Threshold Optimizer</h1>
            <p className="text-gray-600 text-sm">best.pt modelinizi ve data.yaml konfigürasyonunu yükleyerek IoU / Confidence grid araması yapın.</p>
          </div>
          <button
            onClick={handleOptimize}
            disabled={loading}
            className="px-6 py-3 rounded-xl bg-primary-600 text-white font-semibold shadow hover:bg-primary-700 disabled:opacity-60 disabled:cursor-not-allowed"
          >
            {loading ? 'Optimizasyon Çalışıyor...' : 'Optimizasyonu Başlat'}
          </button>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <FileUploader
            label="YOLO best.pt"
            accept=".pt"
            required
            onChange={setBestModel}
            helperText={bestModel ? bestModel.name : 'YOLO eğitiminden çıkan best.pt dosyasını seçin'}
          />
          <FileUploader
            label="data.yaml"
            accept=".yaml,.yml"
            required
            onChange={setDataConfig}
            helperText={dataConfig ? dataConfig.name : 'Dataset konfigürasyon dosyasını yükleyin'}
          />
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <DualRangeInput
            label="IoU Aralığı"
            range={iouRange}
            limits={{ min: 0.1, max: 0.9 }}
            onChange={setIouRange}
          />
          <DualRangeInput
            label="Confidence Aralığı"
            range={confRange}
            limits={{ min: 0.05, max: 0.95 }}
            onChange={setConfRange}
          />
        </div>
      </div>

      {result && (
        <div className="space-y-8">
          <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
            <MetricCard
              title="Recall"
              value={result.best?.recall}
              target={85}
              description="Potluk kaçırma riski"
            />
            <MetricCard
              title="Precision"
              value={result.best?.precision}
              target={75}
              description="Yanlış alarm kontrolü"
            />
            <MetricCard
              title="F1 Skoru"
              value={result.best?.f1}
              target={80}
              description="Denge metriği"
            />
            <div className="border rounded-xl bg-white shadow-sm p-5 space-y-4">
              <h3 className="text-sm font-semibold text-gray-600">Production Hazırlık Skoru</h3>
              <p className="text-3xl font-bold text-primary-600">%{formatNumber(result.production_score)}</p>
              <div className="w-full bg-gray-200 rounded-full h-2">
                <div
                  className="bg-primary-500 h-2 rounded-full"
                  style={{ width: `${Math.min(100, Math.max(0, result.production_score || 0))}%` }}
                />
              </div>
              <p className="text-xs text-gray-500">Recall ağırlıklı skor (0-100). 90+ → Production, 70-90 → iyileştirme önerilir, <70 → yeniden eğitim.</p>
            </div>
          </div>

          <div className="bg-white rounded-2xl shadow p-6 space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="text-xl font-semibold text-gray-800">Heatmap Analizi</h2>
                <p className="text-sm text-gray-500">IoU ve Confidence kombinasyonlarında {activeHeatmapMetric.toUpperCase()} değerleri.</p>
              </div>
              <div className="flex gap-2">
                {['recall', 'precision', 'f1'].map((metric) => (
                  <button
                    key={metric}
                    onClick={() => setActiveHeatmapMetric(metric)}
                    className={`px-3 py-1 rounded-full text-sm font-medium ${
                      activeHeatmapMetric === metric
                        ? 'bg-primary-600 text-white'
                        : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                    }`}
                  >
                    {metric.toUpperCase()}
                  </button>
                ))}
              </div>
            </div>
            <div className="overflow-x-auto">
              <table className="min-w-full border-separate border-spacing-1">
                <thead>
                  <tr>
                    <th className="text-xs text-gray-500 text-left p-2">IoU \ Confidence</th>
                    {uniqueConf.map((conf) => (
                      <th key={conf} className="text-xs text-gray-500 p-2 text-center">{formatNumber(conf)}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {uniqueIoU.map((iou) => (
                    <tr key={iou}>
                      <th className="text-xs text-gray-500 text-left p-2">{formatNumber(iou)}</th>
                      {uniqueConf.map((conf) => renderHeatmapCell(iou, conf))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
            <div className="bg-white rounded-2xl shadow p-6">
              <h2 className="text-lg font-semibold text-gray-800 mb-3">Loss Eğrileri</h2>
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={chartData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                    <XAxis dataKey="epoch" tickLine={false} axisLine={false} />
                    <YAxis tickLine={false} axisLine={false} domain={[0, 'auto']} />
                    <Tooltip formatter={(value) => formatNumber(value, 4)} labelFormatter={(label) => `Epoch ${label}`} />
                    <Legend />
                    <Line type="monotone" dataKey="trainLoss" stroke="#2563eb" strokeWidth={2} dot={false} name="Train Loss" />
                    <Line type="monotone" dataKey="valLoss" stroke="#f97316" strokeWidth={2} dot={false} name="Val Loss" />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
            <div className="bg-white rounded-2xl shadow p-6">
              <h2 className="text-lg font-semibold text-gray-800 mb-3">Precision & Recall Eğrileri</h2>
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={chartData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                    <XAxis dataKey="epoch" tickLine={false} axisLine={false} />
                    <YAxis tickLine={false} axisLine={false} domain={[0, 100]} />
                    <Tooltip formatter={(value) => formatNumber(value)} labelFormatter={(label) => `Epoch ${label}`} />
                    <Legend />
                    <Line type="monotone" dataKey="precision" stroke="#10b981" strokeWidth={2} dot={false} name="Precision" />
                    <Line type="monotone" dataKey="recall" stroke="#ef4444" strokeWidth={2} dot={false} name="Recall" />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>

          <div className="bg-white rounded-2xl shadow p-6">
            <h2 className="text-lg font-semibold text-gray-800 mb-3">mAP Eğrileri</h2>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                  <XAxis dataKey="epoch" tickLine={false} axisLine={false} />
                  <YAxis tickLine={false} axisLine={false} domain={[0, 100]} />
                  <Tooltip formatter={(value) => formatNumber(value)} labelFormatter={(label) => `Epoch ${label}`} />
                  <Legend />
                  <Line type="monotone" dataKey="map50" stroke="#6366f1" strokeWidth={2} dot={false} name="mAP@50" />
                  <Line type="monotone" dataKey="map5095" stroke="#8b5cf6" strokeWidth={2} dot={false} name="mAP@50-95" />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
            <div className="bg-white rounded-2xl shadow p-6 space-y-4">
              <div className="flex items-center justify-between">
                <h2 className="text-lg font-semibold text-gray-800">Confusion Matrix</h2>
                <span className="text-xs text-gray-500">
                  Pozitif örnekler: {result.confusion_matrix?.totals?.positives} • Negatif örnekler: {result.confusion_matrix?.totals?.negatives}
                </span>
              </div>
              <table className="w-full border-collapse">
                <thead>
                  <tr>
                    <th className="border border-gray-200 p-2 text-xs text-gray-500" rowSpan={2}>Gerçek / Tahmin</th>
                    {result.confusion_matrix?.labels?.map((label) => (
                      <th key={label} className="border border-gray-200 p-2 text-xs text-gray-500 text-center" colSpan={1}>{label}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {result.confusion_matrix?.matrix?.map((row, rowIndex) => (
                    <tr key={rowIndex}>
                      <th className="border border-gray-200 p-2 text-xs text-gray-500 text-left">{result.confusion_matrix?.labels?.[rowIndex]}</th>
                      {row.map((value, colIndex) => (
                        <td key={colIndex} className="border border-gray-200 p-2 text-center text-sm font-semibold text-gray-800">
                          {value}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="bg-white rounded-2xl shadow p-6 space-y-4">
              <h2 className="text-lg font-semibold text-gray-800">production_config.yaml</h2>
              <p className="text-sm text-gray-600">
                En iyi eşiklerle üretim yapılandırmasını indirin ve FKT üretim pipeline'ına entegre edin.
              </p>
              <button
                onClick={handleDownloadConfig}
                className="px-5 py-2 rounded-lg bg-primary-600 text-white font-medium hover:bg-primary-700 w-fit"
              >
                Yapılandırmayı indir
              </button>
              <div>
                <h3 className="text-sm font-semibold text-gray-700 mb-2">LLM Analiz Promptu</h3>
                <textarea
                  readOnly
                  value={result.analysis_prompt || ''}
                  className="w-full h-48 text-xs font-mono bg-gray-50 border border-gray-200 rounded-lg p-3 text-gray-700"
                />
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default ThresholdOptimizer;
