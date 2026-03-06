import React, { useState, useEffect } from 'react';
import { getSystemConfig, getConfigSections, saveSystemConfig } from '../../api/config';
import toast from 'react-hot-toast';
import { Settings, Save, AlertCircle, RefreshCw } from 'lucide-react';

export default function SystemConfig() {
  const [sections, setSections] = useState([]);
  const [config, setConfig] = useState({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [activeTab, setActiveTab] = useState('');

  useEffect(() => {
    fetchConfig();
  }, []);

  const fetchConfig = async () => {
    setLoading(true);
    try {
      const [secRes, cfgRes] = await Promise.all([
        getConfigSections(),
        getSystemConfig()
      ]);
      
      if (secRes.data?.ok) {
        setSections(secRes.data.sections || []);
        if (secRes.data.sections.length > 0) {
          setActiveTab(secRes.data.sections[0].key);
        }
      }
      
      if (cfgRes.data?.ok) {
        setConfig(cfgRes.data.config || {});
      }
    } catch (e) {
      toast.error('加载配置失败');
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const res = await saveSystemConfig(config);
      if (res.data?.ok) {
        toast.success('配置保存成功');
        setConfig(res.data.config || config);
      } else {
        toast.error(res.data?.error || '保存失败');
      }
    } catch (e) {
      toast.error('保存出错');
    } finally {
      setSaving(false);
    }
  };

  const handleChange = (sectionKey, fieldKey, value) => {
    setConfig(prev => ({
      ...prev,
      [sectionKey]: {
        ...(prev[sectionKey] || {}),
        [fieldKey]: value
      }
    }));
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[50vh]">
        <RefreshCw className="w-8 h-8 animate-spin text-xy-brand-500" />
      </div>
    );
  }

  const currentSection = sections.find(s => s.key === activeTab);

  return (
    <div className="xy-page max-w-5xl xy-enter">
      <div className="flex flex-col md:flex-row justify-between md:items-end gap-4 mb-6">
        <div>
          <h1 className="xy-title flex items-center gap-2">
            <Settings className="w-6 h-6 text-xy-brand-500" /> 系统与店铺配置
          </h1>
          <p className="xy-subtitle mt-1">管理 AI 提供商、阿里云 OSS 以及自动化相关的核心设置</p>
        </div>
        <button 
          onClick={handleSave} 
          disabled={saving}
          className="xy-btn-primary flex items-center gap-2"
        >
          {saving ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
          保存设置
        </button>
      </div>

      <div className="flex flex-col md:flex-row gap-6">
        {/* 左侧 Tabs */}
        <div className="md:w-64 flex-shrink-0">
          <div className="xy-card overflow-hidden">
            <div className="flex flex-col">
              {sections.map(sec => (
                <button
                  key={sec.key}
                  onClick={() => setActiveTab(sec.key)}
                  className={`text-left px-5 py-4 text-sm font-medium transition-colors border-l-4 ${
                    activeTab === sec.key 
                      ? 'border-l-xy-brand-500 bg-xy-brand-50 text-xy-brand-600' 
                      : 'border-l-transparent text-xy-text-secondary hover:bg-xy-gray-50'
                  }`}
                >
                  {sec.name}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* 右侧内容 */}
        <div className="flex-1">
          {currentSection && (
            <div className="xy-card p-6 animate-in fade-in slide-in-from-right-4">
              <h2 className="text-lg font-bold text-xy-text-primary mb-6 pb-4 border-b border-xy-border">
                {currentSection.name}
              </h2>
              
              <div className="space-y-6 max-w-2xl">
                {currentSection.fields?.map(field => {
                  const sectionData = config[currentSection.key] || {};
                  const value = sectionData[field.key] !== undefined ? sectionData[field.key] : (field.default || '');

                  return (
                    <div key={field.key}>
                      <label className="xy-label flex items-center justify-between">
                        <span>
                          {field.label}
                          {field.required && <span className="text-red-500 ml-1">*</span>}
                        </span>
                      </label>
                      
                      {field.type === 'textarea' ? (
                        <textarea
                          className="xy-input px-3 py-2 h-24"
                          value={value}
                          onChange={(e) => handleChange(currentSection.key, field.key, e.target.value)}
                        />
                      ) : field.type === 'select' ? (
                        <select
                          className="xy-input px-3 py-2"
                          value={value}
                          onChange={(e) => handleChange(currentSection.key, field.key, e.target.value)}
                        >
                          {field.options?.map(opt => (
                            <option key={opt} value={opt}>{opt}</option>
                          ))}
                        </select>
                      ) : field.type === 'toggle' ? (
                        <button
                          className={`w-12 h-6 rounded-full transition-colors relative ${value ? 'bg-green-500' : 'bg-gray-300'}`}
                          onClick={() => handleChange(currentSection.key, field.key, !value)}
                        >
                          <div className={`absolute top-1 bg-white w-4 h-4 rounded-full transition-transform ${value ? 'left-7' : 'left-1'}`}></div>
                        </button>
                      ) : (
                        <input
                          type={field.type || 'text'}
                          className="xy-input px-3 py-2"
                          value={value}
                          onChange={(e) => handleChange(currentSection.key, field.key, e.target.value)}
                        />
                      )}
                    </div>
                  );
                })}
              </div>
              
              {currentSection.key === 'ai' && (
                <div className="mt-8 bg-blue-50 border border-blue-200 p-4 rounded-lg flex items-start gap-3 text-blue-800 text-sm">
                  <AlertCircle className="w-5 h-5 flex-shrink-0 mt-0.5 text-blue-600" />
                  <p>
                    我们推荐使用<strong>百炼千问 (qwen)</strong>，其在处理中文语境和电商营销文案时表现最为稳定。
                    <br/>如果你使用了其他服务商，请确保填入了正确的 Base URL。
                  </p>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
