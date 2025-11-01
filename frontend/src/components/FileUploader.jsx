import React from 'react';

const FileUploader = ({ label, accept, onChange, helperText, required = false }) => {
  const handleChange = (event) => {
    const file = event.target.files && event.target.files[0];
    onChange(file || null);
  };

  return (
    <label className="block">
      <span className="text-sm font-medium text-gray-700">{label}</span>
      <input
        type="file"
        accept={accept}
        required={required}
        onChange={handleChange}
        className="mt-1 block w-full text-sm text-gray-600 file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 file:text-sm file:font-semibold file:bg-primary-50 file:text-primary-700 hover:file:bg-primary-100"
      />
      {helperText && <p className="mt-1 text-xs text-gray-500">{helperText}</p>}
    </label>
  );
};

export default FileUploader;
