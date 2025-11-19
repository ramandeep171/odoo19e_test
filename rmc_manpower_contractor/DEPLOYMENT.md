# 🚀 Deployment Instructions - RMC Manpower Contractor

## Pre-Deployment Checklist

### System Requirements
- ✅ Odoo 19 Enterprise
- ✅ Python 3.10+
- ✅ PostgreSQL 13+
- ✅ wkhtmltopdf (for PDF reports)

### Required Odoo Apps (Install Before Module)
1. Documents (`documents`)
2. Sign (`sign`)
3. HR (`hr`)
4. Approvals (`approvals`)
5. Website (`website`)
6. Accounting (`account`)
7. Indian Localization (`l10n_in`)
8. Fleet (optional - `fleet`)

---

## Installation Steps

### 1. Copy Module to Odoo Addons
```bash
cp -r rmc_manpower_contractor /home/smarterpeak/odoo19/custom_addons/
chown -R odoo:odoo /home/smarterpeak/odoo19/custom_addons/rmc_manpower_contractor
chmod -R 755 /home/smarterpeak/odoo19/custom_addons/rmc_manpower_contractor
```

### 2. Update Odoo Apps List
```bash
# Option A: Via UI
Settings → Activate Developer Mode → Apps → Update Apps List

# Option B: Via CLI
./odoo-bin -c /etc/odoo/odoo.conf -d production_db --update=all --stop-after-init
```

### 3. Install Module
```bash
# Via UI (Recommended)
Apps → Search "RMC Manpower Contractor" → Install

# Via CLI
./odoo-bin -c /etc/odoo/odoo.conf -d production_db -i rmc_manpower_contractor --stop-after-init

# Start Odoo
systemctl restart odoo
```

### 4. Verify Installation
Navigate to: `RMC Contractors` menu
Expected: Menu appears with Agreements submenu

---

## Post-Installation Configuration

### 1. Configure Sign Templates
```
Sign → Configuration → Templates → Create
- Name: RMC Driver Contract Template
- Add signature fields for:
  * Company Representative
  * Contractor
- Save
```

Link template in Agreements:
```
RMC Contractors → Agreements → Agreement Form → Sign Template field
```

### 2. Set Up Chart of Accounts (for TDS)
Ensure TDS account exists:
```
Accounting → Configuration → Chart of Accounts
Search: "206" (TDS Payable)
If not exists: Create
  - Code: 20620
  - Name: TDS Payable - 194C
  - Type: Current Liabilities
```

### 3. Configure System Parameters (Optional)
```
Settings → Technical → System Parameters

Adjust if needed:
- rmc_score.weight_diesel = 0.5
- rmc_score.weight_maintenance = 0.3
- rmc_score.weight_attendance = 0.2
- rmc_score.star_5_threshold = 90
- rmc_billing.bonus_5_star = 10.0
- rmc_billing.penalty_1_star = -10.0
```

### 4. Create User Groups
```
Settings → Users & Companies → Users
Assign users to groups:
- RMC Manager: Full access (Plant Manager, Accounts Head)
- RMC Supervisor: Daily operations (Site Supervisors)
- RMC Contractor User: Own records only (Contractor staff)
```

### 5. Grant Portal Access to Contractors
```
Contacts → Select Contractor → Action → Grant Portal Access
Send invitation email
Contractor can now:
- View agreement at /contract/agreement/<id>
- Complete signature
- Track KPIs
```

---

## Testing in Production

### 1. Create Test Agreement
```
RMC Contractors → Agreements → Create
- Contractor: (create test partner)
- Contract Type: driver_transport
- MGQ Target: 100
- Part-A: 10000
- Part-B: 5000
- Validity: +30 days
- Add Manpower Matrix:
  * Designation: Test Driver
  * Headcount: 1
  * Rate: 10000
  * Remark: Part-A
```

### 2. Test Signature Flow
```
Agreement → Send for Signature
Check email received
Complete signature via link
Verify: Agreement state = 'active'
```

### 3. Create Operational Record
```
Operations → Diesel Logs → Create
- Agreement: (test agreement)
- Opening: 100L
- Issued: 50L
- Closing: 50L
- Work Done: 250km
- Validate
Verify: Efficiency = 5 km/l
```

### 4. Test Monthly Billing
```
Agreement → Prepare Monthly Bill
- Period: Current month
- MGQ Achieved: 95
- Compute → Verify amounts
- Create Vendor Bill
Check: Bill in draft, TDS calculated
```

### 5. Run Automated Tests (Optional)
```bash
./odoo-bin -c /etc/odoo/odoo.conf -d production_db \
  -u rmc_manpower_contractor --test-enable \
  --log-level=test --stop-after-init

Expected: 10/10 tests passed
```

---

## Monitoring & Maintenance

### 1. Monitor Cron Job
```
Settings → Technical → Scheduled Actions
Find: "RMC: Compute Monthly Performance"
Verify: Active, Next run = 1st of month
Check logs after first run:
  tail -f /var/log/odoo/odoo.log | grep "Performance computed"
```

### 2. Monitor Automated Actions
```
Settings → Technical → Automation Rules
Find: "RMC: Activate Agreement on Sign"
Check execution count monthly
```

### 3. Regular Tasks
**Daily:**
- Validate pending diesel/maintenance/attendance entries
- Review payment hold agreements

**Weekly:**
- Check pending signatures
- Review breakdown events

**Monthly (1st):**
- Verify cron execution (performance computation)
- Generate monthly bills for active agreements
- Review star ratings and bonus/penalty

---

## Backup & Recovery

### Backup Module Data
```bash
# Export agreements
pg_dump -h localhost -U odoo -d production_db \
  -t rmc_contract_agreement \
  -t rmc_manpower_matrix \
  -t rmc_diesel_log \
  -t rmc_maintenance_check \
  -t rmc_attendance_compliance \
  -t rmc_breakdown_event \
  -t rmc_inventory_handover \
  > rmc_backup_$(date +%Y%m%d).sql
```

### Restore from Backup
```bash
psql -h localhost -U odoo -d production_db < rmc_backup_20251009.sql
```

---

## Performance Optimization

### 1. Database Indexing
Already included in models:
- agreement.name (index=True)
- All foreign keys auto-indexed

### 2. Cron Optimization
If > 1000 agreements, split cron:
```python
# Modify data/cron.xml interval to weekly + batch process
model.search([('state', '=', 'active')], limit=100).compute_performance()
```

### 3. Report Generation
Pre-generate monthly reports:
```bash
# Add cron to generate PDFs on 28th of month
# Reduces wizard wait time
```

---

## Troubleshooting Production Issues

### Issue: Bills Not Creating
**Debug:**
```python
# In Odoo shell
agreement = env['rmc.contract.agreement'].browse(123)
print(agreement.payment_hold)
print(agreement.payment_hold_reason)
print(agreement.is_signed())
```
**Fix:** Clear holds, validate KPIs, ensure signature

### Issue: Performance Not Computing
**Check:**
```bash
# View cron logs
grep "RMC.*Performance" /var/log/odoo/odoo.log

# Manual trigger
agreement.compute_performance()
```

### Issue: Portal Not Accessible
**Verify:**
- Website app installed
- Contractor has portal user
- URL format: `https://yourdomain.com/contract/agreement/123`

---

## Security Hardening

### 1. Restrict Portal Access
```xml
<!-- Add to record rules if needed -->
<record id="portal_agreement_own_only" model="ir.rule">
  <field name="domain_force">[('contractor_id.user_ids', 'in', user.id)]</field>
</record>
```

### 2. Audit Trail
Enable developer mode → Check chatter messages on sensitive operations

### 3. Payment Approval Chain
Configure approvals app:
```
Approvals → Categories → Create
- Name: RMC Vendor Bill Approval
- Approvers: Supervisor → Manager → Accounts
```

---

## Scaling Considerations

### For 100+ Agreements
- Enable PostgreSQL query optimization
- Consider scheduled report pre-generation
- Batch cron processing

### For Multi-Company
- Module already supports `company_id`
- Set record rules per company
- Configure separate sequences per company

---

## Support & Escalation

### Level 1: User Issues
- Check INSTALL.md quick start
- Verify configuration
- Review troubleshooting section

### Level 2: Technical Issues
- Check module logs
- Run tests to isolate issue
- Review feature checklist

### Level 3: Development
- Contact: support@smarterpeak.com
- Provide: logs, agreement ID, steps to reproduce

---

## Success Metrics

After 1 month of deployment, verify:
- ✅ All active agreements signed
- ✅ Payment holds < 10% of agreements
- ✅ Monthly cron executing successfully
- ✅ Vendor bills generated on time
- ✅ Zero critical errors in logs
- ✅ User adoption (check login analytics)

---

**Module Status: PRODUCTION READY**

Last Updated: 2025-10-09  
Module Version: 19.0.1.0.0  
Deployed By: _________________  
Deployment Date: _________________  
Production URL: _________________  

---

**Congratulations on deploying RMC Manpower Contractor!** 🎉
