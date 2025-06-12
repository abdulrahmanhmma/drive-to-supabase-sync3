import streamlit as st
import pandas as pd
from datetime import datetime
import time
from sync_logic import SyncManager
from utils import get_file_status_emoji

# إعدادات الصفحة
st.set_page_config(
    page_title="مزامنة الملفات - Drive to Supabase",
    page_icon="🔄",
    layout="wide"
)

# العنوان
st.title("🔄 نظام مزامنة الملفات الصوتية")
st.markdown("رفع الملفات من Google Drive إلى Supabase")

# تهيئة حالة الجلسة
if 'sync_results' not in st.session_state:
    st.session_state.sync_results = []

# زر البدء
if st.button("🚀 ابدأ المزامنة", type="primary"):
    try:
        # إنشاء مدير المزامنة
        sync_manager = SyncManager()
        
        with st.spinner("🔐 جاري الاتصال بـ Google Drive..."):
            drive_service, valid_files = sync_manager.get_files_from_drive()
        
        if not valid_files:
            st.warning("❌ لم يتم العثور على ملفات صالحة للمزامنة")
        else:
            st.success(f"✅ تم العثور على {len(valid_files)} ملف صالح")
            
            # شريط التقدم
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            # معالجة الملفات
            results = []
            for i, file in enumerate(valid_files):
                # تحديث التقدم
                progress = (i + 1) / len(valid_files)
                progress_bar.progress(progress)
                status_text.text(f'معالجة: {file["name"]} ({i+1}/{len(valid_files)})')
                
                # معالجة الملف
                result = sync_manager.process_file(drive_service, file)
                result['filename'] = file['name']
                results.append(result)
                
                # تأخير بسيط
                time.sleep(0.1)
            
            # حفظ النتائج
            st.session_state.sync_results = results
            
            st.balloons()
            st.success("✅ انتهت المزامنة!")
            
    except Exception as e:
        st.error(f"❌ خطأ: {str(e)}")

# عرض النتائج
if st.session_state.sync_results:
    # الإحصائيات
    total = len(st.session_state.sync_results)
    success = len([r for r in st.session_state.sync_results if r['status'] == 'success'])
    failed = len([r for r in st.session_state.sync_results if r['status'] == 'error'])
    skipped = len([r for r in st.session_state.sync_results if r['status'] == 'skipped'])
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("📁 إجمالي الملفات", total)
    
    with col2:
        st.metric("✅ نجح", success, f"{(success/total*100):.0f}%" if total > 0 else "0%")
    
    with col3:
        st.metric("⚠️ تم تخطيه", skipped)
    
    with col4:
        st.metric("❌ فشل", failed)
    
    # جدول التفاصيل
    st.subheader("📊 تفاصيل الملفات")
    
    # تحويل النتائج لـ DataFrame
    df_data = []
    for r in st.session_state.sync_results:
        df_data.append({
            'اسم الملف': r['filename'],
            'الحالة': f"{get_file_status_emoji(r['status'])} {r['status']}",
            'الرابط': r.get('url', '-'),
            'السبب': r.get('reason', '-')
        })
    
    df = pd.DataFrame(df_data)
    st.dataframe(df, use_container_width=True)