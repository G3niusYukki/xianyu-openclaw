import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { getTemplates, previewListing, publishListing } from '../../api/listing';
import toast from 'react-hot-toast';
import { Wand2, Image as ImageIcon, Send, RefreshCw, AlertCircle } from 'lucide-react';

export default function AutoPublish() {
  const navigate = useNavigate();
  const [step, setStep] = useState(1);
  const [categories, setCategories] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [formData, setFormData] = useState({
    category: 'exchange',
    name: '',
    price: '',
    features: '',
    extra_info: ''
  });
  const [preview, setPreview] = useState<any>(null);

  useEffect(() => {
    getTemplates()
      .then(res => setCategories(res.data.templates || []))
      .catch(err => {
        console.error(err);
        toast.error('无法加载品类模板');
      });
  }, []);

  const handleGeneratePreview = async () => {
    if (!formData.name || !formData.price) {
      toast.error('请填写商品名称和价格');
      return;
    }
    setLoading(true);
    try {
      const featuresArr = formData.features.split('\n').map(s => s.trim()).filter(Boolean);
      const payload = {
        ...formData,
        price: parseFloat(formData.price),
        features: featuresArr
      };
      
      const res = await previewListing(payload);
      if (res.data?.ok) {
        setPreview(res.data);
        setStep(2);
        toast.success('AI生成与预览成功');
      } else {
        toast.error(res.data?.error || '生成失败');
      }
    } catch (e: any) {
      toast.error(e.message || '生成预览失败');
    } finally {
      setLoading(false);
    }
  };

  const handlePublish = async () => {
    if (!preview) return;
    setLoading(true);
    try {
      const res = await publishListing({ preview_data: preview });
      if (res.data?.ok) {
        toast.success('发布成功');
        setStep(3);
      } else {
        toast.error(res.data?.error || '发布失败');
      }
    } catch (e: any) {
      toast.error(e.message || '发布失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="xy-page max-w-4xl xy-enter">
      <h1 className="xy-title mb-6">AI 智能自动上架</h1>
      
      <div className="flex items-center mb-8 bg-xy-surface p-4 rounded-xl shadow-sm border border-xy-border">
        <div className={`flex items-center ${step >= 1 ? 'text-xy-brand-500' : 'text-xy-text-muted'}`}>
          <div className={`w-8 h-8 rounded-full flex items-center justify-center border-2 font-bold ${step >= 1 ? 'border-xy-brand-500 bg-xy-brand-50' : 'border-xy-text-muted'}`}>1</div>
          <span className="ml-2 font-medium">填写信息</span>
        </div>
        <div className={`flex-1 h-px mx-4 ${step >= 2 ? 'bg-xy-brand-500' : 'bg-xy-border'}`}></div>
        <div className={`flex items-center ${step >= 2 ? 'text-xy-brand-500' : 'text-xy-text-muted'}`}>
          <div className={`w-8 h-8 rounded-full flex items-center justify-center border-2 font-bold ${step >= 2 ? 'border-xy-brand-500 bg-xy-brand-50' : 'border-xy-text-muted'}`}>2</div>
          <span className="ml-2 font-medium">AI生成与预览</span>
        </div>
        <div className={`flex-1 h-px mx-4 ${step >= 3 ? 'bg-xy-brand-500' : 'bg-xy-border'}`}></div>
        <div className={`flex items-center ${step >= 3 ? 'text-xy-brand-500' : 'text-xy-text-muted'}`}>
          <div className={`w-8 h-8 rounded-full flex items-center justify-center border-2 font-bold ${step >= 3 ? 'border-xy-brand-500 bg-xy-brand-50' : 'border-xy-text-muted'}`}>3</div>
          <span className="ml-2 font-medium">上架结果</span>
        </div>
      </div>

      {step === 1 && (
        <div className="xy-card p-6 space-y-5 animate-in fade-in slide-in-from-bottom-2">
          <div>
            <label className="xy-label">商品品类</label>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
              {categories.map(cat => (
                <button
                  key={cat.key}
                  onClick={() => setFormData(prev => ({ ...prev, category: cat.key }))}
                  className={`p-3 rounded-lg border text-sm font-medium transition-colors ${
                    formData.category === cat.key 
                      ? 'border-xy-brand-500 bg-xy-brand-50 text-xy-brand-600' 
                      : 'border-xy-border hover:bg-xy-gray-50 text-xy-text-primary'
                  }`}
                >
                  {cat.name}
                </button>
              ))}
            </div>
          </div>
          
          <div className="grid md:grid-cols-2 gap-5">
            <div>
              <label className="xy-label">商品核心名称 <span className="text-red-500">*</span></label>
              <input
                type="text"
                className="xy-input px-3 py-2"
                placeholder="例如：爱奇艺会员月卡"
                value={formData.name}
                onChange={e => setFormData(prev => ({ ...prev, name: e.target.value }))}
              />
            </div>
            <div>
              <label className="xy-label">价格 (元) <span className="text-red-500">*</span></label>
              <input
                type="number"
                className="xy-input px-3 py-2"
                placeholder="例如：15"
                value={formData.price}
                onChange={e => setFormData(prev => ({ ...prev, price: e.target.value }))}
              />
            </div>
          </div>

          <div>
            <label className="xy-label">核心卖点 / 特性 (每行一条)</label>
            <textarea
              className="xy-input px-3 py-2 h-24 resize-none"
              placeholder={`官方正品秒发\n到账快无封号风险\n支持售后指导`}
              value={formData.features}
              onChange={e => setFormData(prev => ({ ...prev, features: e.target.value }))}
            />
          </div>

          <div>
            <label className="xy-label">给 AI 的附加说明 (可选)</label>
            <textarea
              className="xy-input px-3 py-2 h-16 resize-none"
              placeholder="例如：强调这是个人闲置转让，不可退换"
              value={formData.extra_info}
              onChange={e => setFormData(prev => ({ ...prev, extra_info: e.target.value }))}
            />
          </div>

          <div className="pt-4 flex justify-end">
              <button 
                onClick={handleGeneratePreview}
                disabled={loading}
                className="xy-btn-primary px-6 py-2.5 flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {loading ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Wand2 className="w-4 h-4" />}
                AI 智能生成
              </button>
          </div>
        </div>
      )}

      {step === 2 && preview && (
        <div className="space-y-6 animate-in fade-in slide-in-from-bottom-2">
          {preview.compliance?.blocked && (
            <div className="bg-red-50 border-l-4 border-red-500 p-4 rounded-r-lg flex gap-3 text-red-700">
              <AlertCircle className="w-5 h-5 flex-shrink-0 mt-0.5" />
              <div>
                <p className="font-bold text-sm">合规检查未通过</p>
                <p className="text-sm mt-1">{preview.compliance.message}</p>
              </div>
            </div>
          )}
          
          <div className="grid md:grid-cols-5 gap-6">
            <div className="md:col-span-2 space-y-3">
              <h3 className="font-semibold text-xy-text-primary flex items-center gap-2">
                <ImageIcon className="w-4 h-4" /> 主图预览
              </h3>
              <div className="bg-xy-gray-100 rounded-xl overflow-hidden border border-xy-border relative">
                <div className="aspect-[3/4] flex items-center justify-center">
                  <div className="text-xy-text-secondary text-sm">
                    (图片已生成：{preview.local_images?.length}张)
                  </div>
                </div>
              </div>
            </div>

            <div className="md:col-span-3 space-y-4">
              <div className="xy-card p-5">
                <label className="xy-label text-xy-brand-600 flex items-center gap-1.5"><Wand2 className="w-4 h-4"/> 优化后的标题</label>
                <input 
                  type="text" 
                  className="xy-input px-3 py-2 font-medium" 
                  value={preview.title}
                  onChange={(e) => setPreview({...preview, title: e.target.value})}
                />
                
                <label className="xy-label mt-4 text-xy-brand-600 flex items-center gap-1.5"><Wand2 className="w-4 h-4"/> 商品文案</label>
                <textarea 
                  className="xy-input px-3 py-2 h-48"
                  value={preview.description}
                  onChange={(e) => setPreview({...preview, description: e.target.value})}
                />
              </div>
            </div>
          </div>

          <div className="flex justify-between items-center bg-xy-surface p-4 rounded-xl border border-xy-border shadow-sm">
            <button 
              onClick={() => setStep(1)} 
              className="text-xy-text-secondary hover:text-xy-text-primary px-4 py-2"
              disabled={loading}
            >
              返回修改
            </button>
            <div className="flex gap-3">
              <button 
                onClick={handleGeneratePreview}
                disabled={loading}
                className="xy-btn-secondary px-4 py-2"
              >
                重新生成
              </button>
              <button 
                onClick={handlePublish}
                disabled={loading || preview.compliance?.blocked}
                className="xy-btn-primary px-6 py-2 flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {loading ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                发布到闲鱼
              </button>
            </div>
          </div>
        </div>
      )}

      {step === 3 && (
        <div className="xy-card p-10 text-center animate-in zoom-in-95">
          <div className="w-16 h-16 bg-green-100 rounded-full flex items-center justify-center mx-auto mb-4">
            <Send className="w-8 h-8 text-green-600" />
          </div>
          <h2 className="text-2xl font-bold text-xy-text-primary mb-2">发布成功！</h2>
          <p className="text-xy-text-secondary mb-6">商品已成功推送到闲管家并等待闲鱼平台审核</p>
          <div className="flex justify-center gap-4">
            <button onClick={() => { setFormData(prev => ({...prev, name: ''})); setStep(1); }} className="xy-btn-secondary">
              继续发布
            </button>
            <button onClick={() => navigate('/products')} className="xy-btn-primary">
              查看商品列表
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
