import time

def format_time_remaining(seconds):
    """تحويل الثواني لصيغة مقروءة"""
    if seconds < 60:
        return f"{int(seconds)} ثانية"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{int(minutes)} دقيقة"
    else:
        hours = seconds / 3600
        return f"{hours:.1f} ساعة"

def get_file_status_emoji(status):
    """إرجاع رمز حسب حالة الملف"""
    emojis = {
        'success': '✅',
        'error': '❌',
        'skipped': '⚠️',
        'pending': '⏳',
        'processing': '🔄'
    }
    return emojis.get(status, '❓')

def estimate_time(files_remaining, avg_time_per_file):
    """حساب الوقت المتبقي المتوقع"""
    if avg_time_per_file > 0:
        total_seconds = files_remaining * avg_time_per_file
        return format_time_remaining(total_seconds)
    return "جاري الحساب..."