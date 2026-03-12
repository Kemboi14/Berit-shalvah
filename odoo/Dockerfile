FROM odoo:19.0

# Install required system dependencies
USER root
RUN apt-get update && apt-get install -y \
    python3-pil \
    python3-lxml \
    python3-ldap \
    python3-qrcode \
    python3-vobject \
    python3-requests \
    python3-gevent \
    python3-psycopg2 \
    python3-passlib \
    python3-babel \
    python3-dateutil \
    python3-html2text \
    python3-pytz \
    python3-reportlab \
    python3-num2words \
    python3-ofxparse \
    python3-zeep \
    libldap2-dev \
    libsasl2-dev \
    libtiff5-dev \
    libjpeg-dev \
    libopenjp2-7-dev \
    zlib1g-dev \
    liblcms2-dev \
    libwebp-dev \
    tcl8.6-dev \
    tk8.6-dev \
    python3-matplotlib \
    build-essential \
    wget \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt /tmp/
RUN pip3 install --no-cache-dir -r /tmp/requirements.txt

# Set permissions
RUN chown -R odoo:odoo /opt/odoo && \
    chmod -R 755 /opt/odoo

USER odoo

# Expose port
EXPOSE 8069 8071 8072

# Default command
CMD ["odoo"]
