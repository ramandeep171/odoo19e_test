# RMC Manpower Contractor Integration

**Version:** 19.0.1.0.0  
**Author:** SmarterPeak  
**License:** LGPL-3

## Overview

Complete end-to-end contractor lifecycle management for RMC (Ready-Mix Concrete) and manpower operations. This module integrates HRM-style onboarding with dynamic web agreements, Odoo Sign (mandatory), contract-type-based KPIs, Clause 9 breakdown logic, star-rating performance system, and automated monthly billing with TDS calculation.

## Key Features

### 1. **HRM-Style Contractor Onboarding**
- Multi-stage workflow: Draft → Offer → Negotiation → Registration → Verification → Sign Pending → Active → Suspended/Expired
- Integration with Odoo Sign for mandatory digital signatures
- Dynamic web agreement portal at `/contract/agreement/<id>` for public/portal preview
- Portal contractors can view and sign agreements online

### 2. **Contract Type-Based Operations**
Three contract types with type-specific KPI dependencies:

| Contract Type | Mandatory KPI | Optional KPIs |
|---------------|---------------|---------------|
| **driver_transport** | Diesel Log Efficiency | Maintenance |
| **pump_ops** | Maintenance Compliance | Diesel |
| **accounts_audit** | Attendance/Compliance | Maintenance, Diesel |

### 3. **Designation-Wise Wage Matrix**
- Part-A (Fixed): Base monthly payment for headcount
- Part-B (Variable): Linked to MGQ (Minimum Guaranteed Quantity) achievement
- Flexible shift configuration (Day/Night/Rotational/General)
- Auto-calculates total per designation

### 4. **Clause 9: Breakdown & Force Majeure Logic**
Handles real-world disruption scenarios:
- **Emergency Breakdown / LOTO**: Contractor fault → Part-B deduction proportional to downtime
- **NGT/Government Shutdown**: 50:50 salary share + standby allowance for essential staff
- **Force Majeure**: No deduction if external cause
- **MGQ Fairness**: If MGQ achieved despite shutdown → no deduction

### 5. **Star-Rating Performance System**
- 5-tier rating (⭐ to ⭐⭐⭐⭐⭐) based on weighted KPI scores
- Configurable thresholds via System Parameters
- Performance score = weighted average of:
  - Diesel Efficiency (default 50%)
  - Maintenance Compliance (default 30%)
  - Attendance Compliance (default 20%)
- Star-based bonus/penalty:
  - 5 stars: +10% bonus
  - 4 stars: +5% bonus
  - 3 stars: 0%
  - 2 stars: -5% penalty
  - 1 star: -10% penalty

### 6. **Monthly Automated Billing**
Wizard-driven monthly bill preparation:
- **Part-A**: Sum of fixed manpower costs
- **Part-B**: Variable costs × MGQ achievement %
- **Breakdown Deductions**: Clause 9 penalties
- **Bonus/Penalty**: Star-rating adjustments
- **Material Variance**: Inventory shortage/excess auto-added
- **TDS 194C**: Auto-calculated @ 2% (Indian contractor tax)
- **Supporting Reports**: Attaches PDFs for attendance, diesel, maintenance, breakdown
- **Multi-Level Approvals**: Supervisor → Manager → Finance → Accounts

### 7. **Payment Hold Logic**
Automatic payment blocking when:
- Agreement not signed
- Type-based mandatory KPIs have pending/unvalidated entries
- Performance score below minimum threshold (configurable)
- Pending operational items exist

### 8. **Inventory Handover Reconciliation**
- Track issued vs. returned materials
- Auto-calculate variance (shortage = positive, excess = negative)
- Variance value auto-added to monthly bill as material variance line

## Installation

### Prerequisites
Ensure these Odoo apps are installed and activated:
- ✅ Documents
- ✅ Sign (Odoo Sign)
- ✅ HR
- ✅ Approvals
- ✅ Website
- ✅ Portal
- ✅ Accounting
- ✅ Indian Localization (l10n_in)
- ✅ Fleet (optional, for vehicle tracking)

### Steps
1. Copy `rmc_manpower_contractor` to your Odoo `addons` or `custom_addons` directory
2. Update the app list: `Settings → Apps → Update Apps List`
3. Search for "RMC Manpower Contractor Integration"
4. Click **Install**

## Configuration

### 1. System Parameters
Navigate to: `Settings → Technical → Parameters → System Parameters`

**Performance Weights:**
- `rmc_score.weight_diesel` = 0.5 (50%)
- `rmc_score.weight_maintenance` = 0.3 (30%)
- `rmc_score.weight_attendance` = 0.2 (20%)

**Star Thresholds:**
- `rmc_score.star_5_threshold` = 90
- `rmc_score.star_4_threshold` = 75
- `rmc_score.star_3_threshold` = 60
- `rmc_score.star_2_threshold` = 40
- `rmc_score.min_payment_score` = 40 (below this = payment hold)

**Billing Bonus/Penalty:**
- `rmc_billing.bonus_5_star` = 10.0 (+10%)
- `rmc_billing.bonus_4_star` = 5.0 (+5%)
- `rmc_billing.penalty_2_star` = -5.0 (-5%)
- `rmc_billing.penalty_1_star` = -10.0 (-10%)

### 2. Sign Template Setup
1. Go to: `Sign → Configuration → Templates`
2. Create a template for "RMC Contractor Agreement"
3. Add signature placeholders for both parties
4. Link this template in Agreement form

## Usage Workflow

### Sequence Diagram
```
Contractor Lifecycle:

1. DRAFT
   ↓ Create Agreement + Manpower Matrix
2. OFFER
   ↓ Negotiate terms
3. NEGOTIATION
   ↓ Finalize terms
4. VERIFICATION
   ↓ Verify contractor credentials
5. SIGN PENDING
   ↓ Send for Odoo Sign (mandatory)
   ↓ Contractor signs via portal
6. ACTIVE (Auto-triggered on sign completion)
   ↓ Daily Operations:
   │  - Diesel Logs (driver_transport)
   │  - Maintenance Checks (pump_ops)
   │  - Attendance Compliance (accounts_audit)
   │  - Breakdown Events (Clause 9)
   │  - Inventory Handovers
   ↓ Monthly Cron (1st of month):
   │  - Compute Performance Scores
   │  - Generate Star Ratings
   ↓ Month-End:
7. MONTHLY BILLING WIZARD
   ↓ Computes: Part-A + Part-B + Deductions + Bonus/Penalty + Inventory Variance - TDS
   ↓ Attaches: Attendance, Diesel, Maintenance, Breakdown PDFs
   ↓ Creates: Vendor Bill (Draft)
   ↓ Approval Chain: Supervisor → Manager → Finance → Accounts
   ↓ Post Bill → Payment
8. SUSPENDED (if non-compliance)
   OR
9. EXPIRED (validity_end reached)
```

## Dynamic Web Agreement

### Access
Each agreement has a unique web path: `/contract/agreement/<id>`

### Features
- **Public Access**: Shareable link for preview before signing
- **Portal Access**: Contractors can log in and view their agreements
- **Conditional Clauses**: Shows type-specific KPI clauses dynamically
  - Driver contracts → Diesel efficiency clause visible
  - Pump ops → Maintenance clause visible
  - Accounts → Attendance clause visible
- **Clause 9 Display**: Breakdown/Force Majeure terms always shown
- **Sign Status**: Live signature status with "Complete Signature" button

### Portal User Setup
1. Go to contractor partner: `Contacts → <Contractor> → Grant Portal Access`
2. Send invitation email with portal credentials
3. Contractor logs in, navigates to `/contract/agreement/<id>`
4. Clicks "Complete Signature" → redirected to Odoo Sign portal

## Business Logic Deep-Dive

### Payment Hold Mechanism
```python
payment_hold = TRUE if ANY:
  - Agreement not signed
  - Pending items count > 0 (type-specific)
  - Performance score < min_payment_score
  - No validated KPI entries for contract type
```

### Breakdown Deduction (Clause 9)
```python
if is_mgq_achieved:
    deduction = 0  # MGQ met → no penalty

elif responsibility == 'contractor' and event_type in ['emergency', 'loto']:
    deduction_pct = min(downtime_hr / 720, 1.0)  # 720 hrs/month
    deduction = part_b_variable × deduction_pct

elif event_type == 'ngt' and responsibility == 'govt':
    if standby_staff > 0:
        deduction = part_b_variable × 0.5  # 50:50 share
    else:
        deduction = part_b_variable  # Full deduction

else:
    deduction = 0  # Client/third-party fault
```

### Performance Score Calculation
```python
if contract_type == 'driver_transport':
    diesel_norm = min(avg_diesel_efficiency × 20, 100)  # 5 km/l = 100%
    score = diesel_norm × 0.5 + maintenance_compliance × 0.3

elif contract_type == 'pump_ops':
    score = maintenance_compliance × 0.3 + (diesel_norm × 0.5 if diesel else 0)

elif contract_type == 'accounts_audit':
    score = attendance_compliance × 0.2 + maintenance_compliance × 0.3

performance_score = min(score, 100.0)
```

## Menu Structure
```
RMC Contractors
├── Agreements
├── Operations
│   ├── Diesel Logs
│   ├── Maintenance Checks
│   ├── Attendance Compliance
│   ├── Breakdown Events
│   └── Inventory Handovers
```

## Security Groups
1. **RMC Contractor User**: View/create own records
2. **RMC Supervisor**: Validate records, first-level approval
3. **RMC Manager**: Full access, manage all agreements

## Automated Actions
- **Cron Job** (Monthly, 1st @ 2:00 AM):
  - Computes performance for all active agreements
  - Updates KPIs, scores, and star ratings
  - Generates performance summary PDF

- **Sign Completion Trigger**:
  - Auto-activates agreement when signed
  - Reconciles pending operational entries
  - Clears payment hold if conditions met
  - Notifies Accounts team if ready for billing

## Reporting
- **Performance Summary Report**: PDF with KPIs, stars, payment hold status
- **Monthly Billing Attachments**: Auto-generated PDFs for:
  - Attendance compliance
  - Diesel consumption & efficiency
  - Maintenance checks
  - Breakdown events

## Troubleshooting

### Issue: Payment Hold Not Clearing
**Check:**
1. Agreement is signed (`is_agreement_signed = True`)
2. All type-specific mandatory entries validated
3. Performance score ≥ `rmc_score.min_payment_score`
4. No pending items

### Issue: Diesel Logs Stuck in "Pending Agreement"
**Solution:**
1. Go to Agreement form
2. Click "Send for Signature"
3. Complete signature via Odoo Sign
4. Automated action will auto-validate eligible logs

### Issue: TDS Not Calculating
**Check:**
- Ensure `l10n_in` module is installed
- Verify TDS account (206x series) exists in Chart of Accounts
- Check billing wizard subtotal > 0

## Module Structure
```
rmc_manpower_contractor/
├── __init__.py
├── __manifest__.py
├── models/
│   ├── agreement.py               # Main contract model
│   ├── manpower_matrix.py         # Wage matrix
│   ├── diesel_log.py              # Fuel tracking
│   ├── maintenance.py             # Maintenance checks
│   ├── attendance_compliance.py   # Attendance tracking
│   ├── breakdown_event.py         # Clause 9 events
│   ├── inventory_handover.py      # Material tracking
│   └── payment.py                 # Payment hold validation
├── wizards/
│   └── billing_prepare_wizard.py  # Monthly billing
├── controllers/
│   └── agreement_portal.py        # Web portal routes
├── views/
│   ├── agreement_views.xml
│   ├── diesel_log_views.xml
│   ├── maintenance_check_views.xml
│   ├── attendance_compliance_views.xml
│   ├── breakdown_event_views.xml
│   ├── inventory_handover_views.xml
│   ├── manpower_matrix_views.xml
│   ├── website_templates.xml      # Dynamic web agreement
│   └── menuitems.xml
├── data/
│   ├── config_parameters.xml      # System params
│   ├── cron.xml                   # Monthly cron
│   ├── automated_action.xml       # Sign trigger
│   └── sign_template_data.xml
├── security/
│   ├── security_groups.xml
│   ├── ir.model.access.csv
│   └── record_rules.xml
├── reports/
│   ├── performance_report.xml
│   └── monthly_summary_templates.xml
├── demo/
│   └── demo_data.xml
├── tests/
│   └── test_agreement_integration.py
└── static/
    ├── description/
    │   └── icon.png
    └── src/css/
        └── agreement_portal.css
```

## API / Extension Points

### Hooks for Custom Modules
```python
# Override performance computation
class RmcContractAgreement(models.Model):
    _inherit = 'rmc.contract.agreement'
    
    def compute_performance(self):
        super().compute_performance()
        # Add custom KPI logic here

# Add custom billing line
class RmcBillingPrepareWizard(models.TransientModel):
    _inherit = 'rmc.billing.prepare.wizard'
    
    def _create_invoice_lines(self, bill):
        super()._create_invoice_lines(bill)
        # Add custom line items
```

## Changelog

### Version 19.0.1.0.0 (Initial Release)
- Complete contractor lifecycle management
- Odoo Sign integration
- Type-based KPI system
- Clause 9 breakdown logic
- Star-rating performance
- Automated monthly billing with TDS
- Inventory variance tracking
- Dynamic web agreements
- Multi-level approvals
- Comprehensive tests

## Support

For issues, feature requests, or questions:
- **Email:** support@smarterpeak.com
- **Documentation:** See inline docstrings in Python files
- **Tests:** Run `odoo-bin -c odoo.conf -u rmc_manpower_contractor --test-enable --stop-after-init`

## Credits

**Developer:** SmarterPeak Team  
**Odoo Version:** 19.0 Enterprise  
**License:** LGPL-3

---

**Made with ❤️ for RMC Operations Excellence**
