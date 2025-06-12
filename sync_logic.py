import os
import io
from datetime import datetime
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from supabase import create_client, Client
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
import pickle
import streamlit as st

# نطاقات Google Drive
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']

class SyncManager:
    def __init__(self):
        # قراءة البيانات من Streamlit Secrets
        try:
            # استخدام Streamlit Secrets
            self.SUPABASE_URL = st.secrets["SUPABASE_URL"]
            self.SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
            self.BUCKET_NAME = st.secrets["BUCKET_NAME"]
            self.FOLDER_ID = st.secrets["FOLDER_ID"]
        except:
            # قيم افتراضية للتطوير المحلي
            self.SUPABASE_URL = 'https://pcdtbypsrwajehvdjege.supabase.co'
            self.SUPABASE_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InBjZHRieXBzcndhamVodmRqZWdlIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc0OTU4MjMzNywiZXhwIjoyMDY1MTU4MzM3fQ.eEMMnND9rdNJ2qIi26zjnIYqqNBDpbdD4Q5AKywJORQ'
            self.BUCKET_NAME = 'audio-files'
            self.FOLDER_ID = os.getenv('FOLDER_ID', '')
        
        # إعداد Supabase
        self.supabase = create_client(self.SUPABASE_URL, self.SUPABASE_KEY)
        
    def authenticate_google(self):
        """المصادقة مع Google Drive باستخدام Service Account"""
        from google.oauth2 import service_account
        import json
        
        # جلب بيانات Service Account من Streamlit Secrets
        try:
            # محاولة قراءة من ملف محلي أولاً (للتطوير)
            credentials = service_account.Credentials.from_service_account_file(
                'credentials.json',
                scopes=SCOPES
            )
        except:
            # إذا فشل، استخدم Streamlit Secrets
            # تحويل Streamlit Secrets إلى dictionary
            service_account_info = dict(st.secrets["gcp_service_account"])
            credentials = service_account.Credentials.from_service_account_info(
                service_account_info,
                scopes=SCOPES
            )
        
        # بناء خدمة Drive
        return build('drive', 'v3', credentials=credentials)
        
    def is_valid_filename(self, name):
        """التحقق من صحة اسم الملف"""
        if not (name.endswith('.mp3') or name.endswith('.wav')):
            return False
        if '(' in name or ')' in name or ' ' in name:
            return False
        parts = name.rsplit('.', 1)[0].split('-')
        return len(parts) == 5
    
    def parse_filename(self, filename):
        """استخراج المعلومات من اسم الملف
        الصيغة المتوقعة: YYYYMMDD-HHMMSS-CODE-EXT-PHONE.mp3
        """
        # إزالة الامتداد
        name_without_ext = filename.rsplit('.', 1)[0]
        
        # تقسيم الاسم على الشرطات
        parts = name_without_ext.split('-')
        
        if len(parts) == 5:
            # تحويل التاريخ من YYYYMMDD إلى YYYY-MM-DD
            date_str = parts[0]
            if len(date_str) == 8:
                formatted_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
            else:
                formatted_date = date_str
            
            # تحويل الوقت من HHMMSS إلى HH:MM:SS
            time_str = parts[1]
            if len(time_str) == 6:
                formatted_time = f"{time_str[:2]}:{time_str[2:4]}:{time_str[4:6]}"
            else:
                formatted_time = time_str
            
            return {
                'event_date': formatted_date,      # تاريخ المكالمة
                'event_time': formatted_time,      # وقت المكالمة
                'reference_code': parts[2],        # ترميز
                'extension_id': parts[3],          # رقم التحويلة
                'contact_number': parts[4]         # رقم الجوال
            }
        return None
    
    def download_from_drive(self, service, file_id):
        """تحميل ملف من Google Drive"""
        request = service.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
        fh.seek(0)
        return fh
    
    def check_file_exists(self, filename):
        """التحقق من وجود الملف في قاعدة البيانات الجديدة"""
        try:
            # استخدام Function للقراءة الآمنة
            result = self.supabase.rpc('get_data_records').execute()
            
            # البحث عن الملف في النتائج
            resource_name = filename.rsplit('.', 1)[0]
            for record in result.data:
                if record.get('resource_name') == resource_name:
                    return True
            
            return False
        except Exception as e:
            print(f"خطأ في التحقق من وجود الملف: {str(e)}")
            return False
    
    def process_file(self, drive_service, file):
        """معالجة ملف واحد"""
        try:
            # التحقق من وجود الملف أولاً
            if self.check_file_exists(file['name']):
                return {'status': 'skipped', 'reason': 'الملف موجود مسبقاً في قاعدة البيانات'}
            
            # استخراج المعلومات من اسم الملف
            file_info = self.parse_filename(file['name'])
            if not file_info:
                return {'status': 'error', 'reason': 'فشل في تحليل اسم الملف'}
            
            # تحميل من Drive
            file_content = self.download_from_drive(drive_service, file['id'])
            
            # رفع إلى Supabase Storage
            path_in_bucket = f"Pro2025v1/{file['name']}"
            temp_file = f"/tmp/{file['name']}"
            
            # حفظ مؤقت
            os.makedirs('/tmp', exist_ok=True)
            with open(temp_file, "wb") as f:
                f.write(file_content.read())
            
            # رفع للـ bucket
            try:
                self.supabase.storage.from_(self.BUCKET_NAME).upload(path_in_bucket, temp_file)
            except Exception as upload_error:
                error_msg = str(upload_error).lower()
                if "duplicate" in error_msg or "already exists" in error_msg:
                    # إذا كان الملف موجود في Storage، احصل على الرابط مباشرة
                    pass
                elif "storage limit" in error_msg:
                    os.remove(temp_file)
                    return {'status': 'error', 'reason': 'تجاوز حد التخزين'}
                elif "invalid file" in error_msg:
                    os.remove(temp_file)
                    return {'status': 'error', 'reason': 'نوع الملف غير مدعوم'}
                else:
                    os.remove(temp_file)
                    return {'status': 'error', 'reason': f'خطأ في الرفع: {str(upload_error)[:100]}'}
            
            os.remove(temp_file)
            
            # الحصول على الرابط العام
            public_url = self.supabase.storage.from_(self.BUCKET_NAME).get_public_url(path_in_bucket)
            
            # إزالة علامة الاستفهام من النهاية إن وجدت
            if public_url.endswith('?'):
                public_url = public_url[:-1]
            
            # إعداد البيانات للإدخال في قاعدة البيانات الجديدة
            # استخدام Function add_data_record مع الأعمدة الجديدة
            record_data = {
                "resource_name": file['name'].rsplit('.', 1)[0],  # اسم الملف بدون الامتداد
                "content_url": public_url,                         # رابط الملف
                "event_date": file_info['event_date'],           # تاريخ المكالمة
                "event_time": file_info['event_time'],           # وقت المكالمة
                "reference_code": file_info['reference_code'],    # ترميز
                "extension_id": file_info['extension_id'],        # رقم التحويلة
                "contact_number": file_info['contact_number'],    # رقم الجوال
                "category_type": "incoming"                        # نوع المكالمة (يمكنك تعديله حسب الحاجة)
            }
            
            # استخدام Function للإدخال الآمن
            result = self.supabase.rpc('add_data_record', record_data).execute()
            
            if result.data:
                return {'status': 'success', 'url': public_url}
            else:
                return {'status': 'error', 'reason': 'فشل في إضافة السجل لقاعدة البيانات'}
            
        except Exception as e:
            return {'status': 'error', 'reason': str(e)}
    
    def get_files_from_drive(self):
        """جلب قائمة الملفات من Google Drive"""
        drive_service = self.authenticate_google()
        
        # البحث عن الملفات في المجلد
        query = f"'{self.FOLDER_ID}' in parents and trashed = false"
        results = drive_service.files().list(
            q=query, 
            fields="files(id, name, mimeType)"
        ).execute()
        
        files = results.get('files', [])
        
        # فلترة الملفات الصالحة
        valid_files = []
        for file in files:
            if self.is_valid_filename(file['name']):
                valid_files.append(file)
        
        return drive_service, valid_files