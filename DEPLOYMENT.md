# Production Deployment Checklist

## 🔒 Security Checklist

- [ ] **SECRET_KEY**: Set strong, unique secret key (not default)
- [ ] **Environment Variables**: All sensitive data in environment variables
- [ ] **Debug Mode**: Disabled in production (`FLASK_ENV=production`)
- [ ] **HTTPS**: Enabled with proper SSL certificates
- [ ] **Security Headers**: Implemented (XSS, CSRF, Frame protection)
- [ ] **Input Validation**: All user inputs validated and sanitized
- [ ] **Admin Password**: Default admin password changed
- [ ] **Database**: Proper database with backups configured
- [ ] **Google Credentials**: Secure storage of API credentials
- [ ] **Logs**: Sensitive information not logged

## 🚀 Performance Checklist

- [ ] **Database Indexing**: Proper indexes on frequently queried fields
- [ ] **Static Files**: Properly served (CDN in production)
- [ ] **Caching**: Implement caching strategy
- [ ] **Database Connection Pooling**: Configure for high traffic
- [ ] **Background Jobs**: Scheduler configured properly
- [ ] **Error Handling**: Comprehensive error handling
- [ ] **Monitoring**: Application monitoring setup
- [ ] **Load Testing**: Application tested under load

## 📋 Deployment Steps

### 1. Pre-Deployment Setup

```bash
# Clone repository
git clone <your-repo-url>
cd "slot booking app"

# Set up environment
cp .env.example .env
# Edit .env with production values
```

### 2. Database Setup

```bash
# Run production setup script
python startup.py

# Verify admin user created
# Login with admin/admin123 and change password
```

### 3. Google Calendar Setup

```bash
# Place google_credentials.json in project root
# Verify Google Calendar API is enabled
# Test calendar integration
```

### 4. Production Deployment (Render.com)

```bash
# Push to GitHub
git add .
git commit -m "Production ready deployment"
git push origin main

# Connect to Render.com
# Import repository
# Render will use render.yaml automatically
```

### 5. Environment Variables (Render Dashboard)

```
SECRET_KEY=<generate-strong-key>
FLASK_ENV=production
FORCE_HTTPS=true
ADMIN_EMAIL=your-admin@domain.com
```

### 6. Post-Deployment Verification

- [ ] Application loads without errors
- [ ] Login functionality works
- [ ] Admin panel accessible
- [ ] Slot creation/booking works
- [ ] Google Calendar integration works
- [ ] Mobile responsiveness verified
- [ ] Error pages display correctly
- [ ] Logs are being generated
- [ ] Background jobs running

## 🔧 Maintenance Tasks

### Daily
- [ ] Check application logs
- [ ] Verify scheduled jobs running
- [ ] Monitor error rates

### Weekly
- [ ] Database backup
- [ ] Review security logs
- [ ] Performance monitoring

### Monthly
- [ ] Update dependencies
- [ ] Security audit
- [ ] Capacity planning review

## 🆘 Emergency Procedures

### Application Down
1. Check server status
2. Review recent logs
3. Check database connectivity
4. Verify environment variables
5. Restart application if needed

### Data Recovery
1. Stop application
2. Restore from latest backup
3. Run database migrations
4. Test functionality
5. Resume application

### Security Incident
1. Immediately change all passwords
2. Review access logs
3. Update security keys
4. Notify users if needed
5. Document incident

## 📞 Support Contacts

- **Technical Lead**: [Contact Info]
- **Database Admin**: [Contact Info]  
- **Security Team**: [Contact Info]
- **Hosting Provider**: [Render Support]

---

**Last Updated**: {{ date }}
**Deployment Version**: {{ version }}
