# Installation & Quick Start Guide

## Quick Installation

### 1. Prerequisites Check
```bash
# Ensure Odoo 19 Enterprise is running
# Required apps: Documents, Sign, HR, Approvals, Website, Portal, Accounting, l10n_in

# Verify module location
ls -la /home/smarterpeak/odoo19/custom_addons/rmc_manpower_contractor/
```

### 2. Install Module
```bash
# Option A: Via Odoo UI
1. Settings → Apps → Update Apps List
2. Search: "RMC Manpower Contractor"
3. Click Install

# Option B: Via Command Line
./odoo-bin -c odoo.conf -u rmc_manpower_contractor -d your_database --stop-after-init
```

### 3. Activate Required Apps
Go to `Settings → Apps` and ensure these are installed:
- ✅ Documents
- ✅ Sign
- ✅ Website
- ✅ Accounting
- ✅ Indian Localization

### 4. Configure System Parameters (Optional)
`Settings → Technical → System Parameters`
- Adjust performance weights
- Set star rating thresholds
- Configure bonus/penalty percentages

## Quick Start (5 Minutes)

### Step 1: Create Contractor Partner
```
Contacts → Create
- Name: "ABC Transport Services"
- Mark as Vendor: ✓
- Email: contractor@example.com
```

### Step 2: Create Agreement
```
RMC Contractors → Agreements → Create
- Contractor: ABC Transport Services
- Contract Type: Driver Transport
- MGQ Target: 1000 m³
- Part-A Fixed: 50,000
- Part-B Variable: 30,000
- Validity: Today + 1 year
```

### Step 3: Add Manpower Matrix
```
In Agreement Form → Manpower Matrix Tab
- Designation: Driver
- Headcount: 5
- Shift: Day
- Base Rate: 10,000
- Remark: Part-A (Fixed)
```

### Step 4: Send for Signature
```
Agreement Form → Send for Signature button
- Select Sign Template
- System sends email to contractor
```

### Step 5: Create Operational Records
**After signature is completed:**

#### Diesel Log (for driver_transport)
```
RMC Contractors → Operations → Diesel Logs → Create
- Agreement: (select created agreement)
- Date: Today
- Opening: 100L
- Issued: 50L
- Closing: 50L
- Work Done (km): 250 km
- Click Validate
```

#### Maintenance Check (for pump_ops)
```
Operations → Maintenance Checks → Create
- Agreement: (select)
- Checklist OK: 95%
- Repaired: Yes
```

#### Attendance (for accounts_audit)
```
Operations → Attendance Compliance → Create
- Agreement: (select)
- Present Headcount: 8 (out of 10)
- Documents OK: Yes
- Supervisor OK: Yes
```

### Step 6: Monthly Billing (End of Month)
```
Agreement Form → Prepare Monthly Bill button
1. Set Period: Start & End dates
2. Enter MGQ Achieved: 950 m³
3. Click "Compute Amounts"
4. Review breakdown
5. Click "Create Vendor Bill"
6. Bill created in draft → ready for approval
```

## Testing

### Run Automated Tests
```bash
./odoo-bin -c odoo.conf -d test_db -i rmc_manpower_contractor --test-enable --stop-after-init
```

Expected output:
```
test_01_unsigned_agreement_blocks_validation ... ok
test_02_payment_hold_when_unsigned ... ok
test_03_performance_computation_driver_type ... ok
test_04_breakdown_deduction_calculation ... ok
test_05_breakdown_no_deduction_if_mgq_achieved ... ok
test_06_inventory_variance_computation ... ok
test_07_star_rating_computation ... ok
test_08_manpower_matrix_total ... ok
test_09_attendance_compliance_calculation ... ok
test_10_contract_type_immutable_after_sign ... ok

Ran 10 tests in 2.5s - OK
```

## Portal Setup for Contractors

### Grant Portal Access
```
1. Go to Contractor partner
2. Action → Grant Portal Access
3. Send Invitation
4. Contractor receives email with login link
```

### Contractor Portal Features
- View agreement at: `/contract/agreement/<id>`
- See performance dashboard
- Complete signature via Odoo Sign
- Track KPIs (diesel/maintenance/attendance)
- View monthly bills

## Troubleshooting

### Module Not Appearing in Apps List
```bash
# Check module path
ls -la custom_addons/rmc_manpower_contractor/__manifest__.py

# Restart Odoo
sudo systemctl restart odoo

# Update apps list
Settings → Apps → Update Apps List (with dev mode ON)
```

### Sign Integration Not Working
```
1. Ensure 'Sign' app is installed
2. Settings → Sign → Configuration
3. Create Sign Template
4. Link template in Agreement form
```

### Payment Hold Not Clearing
```
Debug checklist:
1. Agreement.is_agreement_signed → True?
2. Agreement.pending_items_count → 0?
3. Agreement.performance_score ≥ 40?
4. Type-specific KPIs validated?

Fix: Agreement Form → Recompute Performance
```

## Uninstall (if needed)
```bash
./odoo-bin -c odoo.conf -d your_db --uninstall rmc_manpower_contractor
```

## Next Steps
- Configure bonus/penalty percentages in System Parameters
- Set up approval workflow users
- Create Sign templates for different contract types
- Configure TDS accounts in Chart of Accounts
- Import contractor master data

---
**Ready to use! Start with demo data or create your first real agreement.**
