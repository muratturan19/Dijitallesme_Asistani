import React, { useState } from 'react';
import { ToastContainer } from 'react-toastify';
import 'react-toastify/dist/ReactToastify.css';
import WelcomeWizard from './components/WelcomeWizard';
import FieldMapper from './components/FieldMapper';
import BatchUpload from './components/BatchUpload';
import Dashboard from './components/Dashboard';

function App() {
  const [currentView, setCurrentView] = useState('dashboard');
  const [wizardData, setWizardData] = useState(null);
  const [selectedTemplate, setSelectedTemplate] = useState(null);

  const handleWizardComplete = (data) => {
    setWizardData(data);
    setCurrentView('fieldMapper');
  };

  const handleFieldMapperComplete = (data) => {
    setWizardData(data);
    setCurrentView('batchUpload');
  };

  const handleBatchComplete = () => {
    setCurrentView('dashboard');
    setWizardData(null);
    setSelectedTemplate(null);
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

  const handleBackToWizard = () => {
    setCurrentView('wizard');
  };

  return (
    <div className="min-h-screen bg-gray-100">
      {/* Header */}
      <header className="bg-white shadow-sm">
        <div className="max-w-7xl mx-auto px-4 py-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between">
            <div className="flex items-center">
              <h1
                className="text-2xl font-bold text-primary-600 cursor-pointer"
                onClick={() => setCurrentView('dashboard')}
              >
                📄 Dijitalleşme Asistanı
              </h1>
            </div>
            <nav className="flex gap-4">
              <button
                onClick={() => setCurrentView('dashboard')}
                className={`px-4 py-2 rounded ${
                  currentView === 'dashboard'
                    ? 'bg-primary-600 text-white'
                    : 'text-gray-600 hover:bg-gray-100'
                }`}
              >
                Ana Sayfa
              </button>
              <button
                onClick={handleNewTemplate}
                className={`px-4 py-2 rounded ${
                  currentView === 'wizard'
                    ? 'bg-primary-600 text-white'
                    : 'text-gray-600 hover:bg-gray-100'
                }`}
              >
                Yeni Şablon
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
          />
        )}
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
