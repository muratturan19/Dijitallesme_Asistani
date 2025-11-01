import React, { useMemo, useState } from 'react';
import { ToastContainer } from 'react-toastify';
import 'react-toastify/dist/ReactToastify.css';
import WelcomeWizard from './components/WelcomeWizard';
import FieldMapper from './components/FieldMapper';
import BatchUpload from './components/BatchUpload';
import Dashboard from './components/Dashboard';
import TemplateLearningView from './components/TemplateLearningView';
import ThresholdOptimizer from './components/ThresholdOptimizer';

function App() {
  const [currentView, setCurrentView] = useState('dashboard');
  const [wizardData, setWizardData] = useState(null);
  const [selectedTemplate, setSelectedTemplate] = useState(null);
  const [dashboardSection, setDashboardSection] = useState('overview');
  const [learningDefaults, setLearningDefaults] = useState({});

  const handleWizardComplete = (data) => {
    setWizardData(data);
    setCurrentView('fieldMapper');
  };

  const handleFieldMapperComplete = (data) => {
    setWizardData(data);
    setCurrentView('batchUpload');
  };

  const handleBatchComplete = () => {
    setDashboardSection('overview');
    setCurrentView('dashboard');
    setWizardData(null);
    setSelectedTemplate(null);
    setLearningDefaults({});
  };

  const handleNewTemplate = () => {
    setWizardData(null);
    setSelectedTemplate(null);
    setCurrentView('wizard');
  };

  const handleSelectTemplate = (template) => {
    setSelectedTemplate(template);
    setCurrentView('batchUpload');
  };

  const handleResumeBatch = (templateId) => {
    setSelectedTemplate(templateId ? { id: templateId } : null);
    setWizardData(null);
    setCurrentView('batchUpload');
  };

  const handleBackToWizard = () => {
    setCurrentView('wizard');
  };

  const handleShowDashboard = (section = 'overview') => {
    setDashboardSection(section);
    setCurrentView('dashboard');
  };

  const handleOpenLearning = (defaults = {}) => {
    setLearningDefaults(defaults);
    setCurrentView('learning');
  };

  const isViewActive = useMemo(
    () => ({
      wizard: currentView === 'wizard' || currentView === 'fieldMapper',
      batch: currentView === 'batchUpload' || (currentView === 'dashboard' && dashboardSection === 'pending'),
      learning: currentView === 'learning',
      optimizer: currentView === 'optimizer',
    }),
    [currentView, dashboardSection]
  );

  return (
    <div className="min-h-screen bg-gray-100">
      {/* Header */}
      <header className="bg-white shadow-sm">
        <div className="max-w-7xl mx-auto px-4 py-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between">
            <div className="flex items-center">
              <h1
                className="text-2xl font-bold text-primary-600 cursor-pointer"
                onClick={() => handleShowDashboard('overview')}
              >
                📄 Dijitalleşme Asistanı
              </h1>
            </div>
            <nav className="flex gap-4">
              <button
                onClick={handleNewTemplate}
                className={`px-4 py-2 rounded ${
                  isViewActive.wizard
                    ? 'bg-primary-600 text-white'
                    : 'text-gray-600 hover:bg-gray-100'
                }`}
              >
                Yeni Şablon Oluştur
              </button>
              <button
                onClick={() => handleShowDashboard('pending')}
                className={`px-4 py-2 rounded ${
                  isViewActive.batch
                    ? 'bg-primary-600 text-white'
                    : 'text-gray-600 hover:bg-gray-100'
                }`}
              >
                Toplu Yükleme Devam
              </button>
              <button
                onClick={handleOpenLearning}
                className={`px-4 py-2 rounded ${
                  isViewActive.learning
                    ? 'bg-primary-600 text-white'
                    : 'text-gray-600 hover:bg-gray-100'
                }`}
              >
                Şablonu İyileştir
              </button>
              <button
                onClick={() => setCurrentView('optimizer')}
                className={`px-4 py-2 rounded ${
                  isViewActive.optimizer
                    ? 'bg-primary-600 text-white'
                    : 'text-gray-600 hover:bg-gray-100'
                }`}
              >
                Threshold Optimize Et
              </button>
            </nav>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="py-8">
        {currentView === 'dashboard' && (
          <Dashboard
            onNewTemplate={handleNewTemplate}
            onSelectTemplate={handleSelectTemplate}
            onResumeBatch={handleResumeBatch}
            activeSection={dashboardSection}
          />
        )}

        {currentView === 'wizard' && (
          <WelcomeWizard onComplete={handleWizardComplete} />
        )}

        {currentView === 'fieldMapper' && wizardData && (
          <FieldMapper
            data={wizardData}
            onNext={handleFieldMapperComplete}
            onBack={handleBackToWizard}
          />
        )}

        {currentView === 'batchUpload' && (
          <BatchUpload
            templateId={wizardData?.templateId || selectedTemplate?.id}
            onComplete={handleBatchComplete}
            onStartCorrection={(payload) =>
              handleOpenLearning({
                ...payload,
                templateId: wizardData?.templateId || selectedTemplate?.id,
              })
            }
          />
        )}

        {currentView === 'learning' && (
          <TemplateLearningView
            onBack={() => handleShowDashboard('overview')}
            initialDocumentId={learningDefaults.documentId}
            initialFieldId={learningDefaults.fieldId}
            initialTemplateId={learningDefaults.templateId}
          />
        )}

        {currentView === 'optimizer' && <ThresholdOptimizer />}
      </main>

      {/* Toast Notifications */}
      <ToastContainer
        position="top-right"
        autoClose={3000}
        hideProgressBar={false}
        newestOnTop
        closeOnClick
        rtl={false}
        pauseOnFocusLoss
        draggable
        pauseOnHover
      />
    </div>
  );
}

export default App;
