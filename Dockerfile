# ==============================================================================
# Tahap 1: Build Stage - Menginstal dependensi
# ==============================================================================
# Gunakan image Python lengkap untuk mengkompilasi dependensi jika diperlukan [cite: 1]
FROM python:3.11-slim as builder

# Set environment variables [cite: 1]
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Instal dependensi sistem yang dibutuhkan untuk build [cite: 1]
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Set work directory
WORKDIR /app

# Buat virtual environment untuk isolasi dependensi
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Salin file requirements terlebih dahulu untuk caching [cite: 3]
COPY requirements.txt .

# Instal dependensi Python ke dalam virtual environment [cite: 3]
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ==============================================================================
# Tahap 2: Final Stage - Image produksi yang ramping
# ==============================================================================
# Mulai dari image slim yang bersih [cite: 1]
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Instal HANYA dependensi sistem yang dibutuhkan saat runtime [cite: 1, 2]
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libopus-dev \
    libwebp-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Set work directory
WORKDIR /app

# Salin virtual environment dari build stage
COPY --from=builder /opt/venv /opt/venv

# Salin kode bot
COPY bot.py . 

# Buat pengguna non-root untuk keamanan 
RUN useradd -m -r -u 1000 botuser && \
    chown -R botuser:botuser /app

# Ganti ke pengguna non-root 
USER botuser

# Buat direktori sessions yang dimiliki oleh botuser 
RUN mkdir -p /app/sessions

# Atur PATH agar menggunakan Python dari venv
ENV PATH="/opt/venv/bin:$PATH"

# Expose port untuk health check Kinsta [cite: 5]
EXPOSE 8080

# Health check (opsional, tapi bagus untuk Kinsta) [cite: 5]
# HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
#     CMD curl -f http://localhost:8080/ || exit 1
# Catatan: Healthcheck di-disable karena bot ini tidak memiliki server web.
# Kinsta akan memonitor prosesnya secara langsung.

# Perintah untuk menjalankan bot [cite: 5]
CMD ["python", "bot.py"]
