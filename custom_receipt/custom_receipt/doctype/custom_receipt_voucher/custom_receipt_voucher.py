import frappe
from frappe.model.document import Document

class CustomReceiptVoucher(Document):
    def validate(self):
        total_allocated_amount = sum(row.allocated_amount for row in self.receipt_details)
        self.total_allocated_amount = total_allocated_amount
        total_addition_or_deduction_amount = sum(row.amount for row in self.addition_or_deduction_details)
        self.total_addition_or_deduction_amount = total_addition_or_deduction_amount
        total_amount = total_allocated_amount + total_addition_or_deduction_amount
        self.total_amount = total_amount
    
    def before_submit(self):
        if self.entry_type in ['Bank', 'Cash']:
            # Create Journal Entry for Bank Entry
            journal_entry = frappe.get_doc({
                'doctype': 'Journal Entry',
				'voucher_type': f"{self.entry_type} Entry",
                'posting_date': self.posting_date,
				'cheque_no':self.reference,
				'cheque_date':self.posting_date,
				'user_remark': self.remarks,
				'custom_custom_receipt_voucher': self.name,
                'accounts': [
                    {
                        'account': self.paid_to,
                        'debit_in_account_currency': self.total_amount,
                        'credit_in_account_currency': 0
                    }
                ]
            })

            # Add rows from receipt_details
            for row in self.receipt_details:
                if row.allocated_amount < 0:
                    debit_amount = abs(row.allocated_amount)
                    credit_amount = 0
                else:
                    debit_amount = 0
                    credit_amount = abs(row.allocated_amount)
                
                journal_entry.append('accounts', {
                    'account': 'Debtors - HT',
                    'party_type': 'Customer',
                    'party': row.party,
                    'debit_in_account_currency': debit_amount,
                    'credit_in_account_currency': credit_amount,
                    'reference_type': row.reference_doctype,
                    'reference_name': row.reference_voucher
                })

            # Add rows from addition_or_deduction_details
            for row in self.addition_or_deduction_details:
                if row.amount < 0:
                    d_amount = abs(row.amount)
                    c_amount = 0
                else:
                    d_amount = 0
                    c_amount= abs(row.amount)
                # Ensure row.amount is positive
                amount = abs(row.amount)
                
                journal_entry.append('accounts', {
                    'account': row.account,
                    'debit_in_account_currency': d_amount,
                    'credit_in_account_currency': c_amount,
                    'user_remark': row.customer or ""
                })

            # Save and submit Journal Entry
            journal_entry.insert()
            journal_entry.submit()
            self.journal_entry = journal_entry.name  # Set journal entry number into self.journal_entry field
            frappe.msgprint(f"Journal Entry created: {journal_entry.name}")

    def on_cancel(self):
        if self.journal_entry:
            # Load the Journal Entry document to cancel and delete
            journal_entry = frappe.get_doc("Journal Entry", self.journal_entry)
            
            # Cancel the Journal Entry
            journal_entry.cancel()
            
            frappe.msgprint(f"Journal Entry {self.journal_entry} canceled and deleted.")
            self.journal_entry = None	


@frappe.whitelist()
def fetch_gl_entries(invoice_from_date, invoice_to_date, customer=None, customer_group=None):
    # Validate input
    if not (invoice_from_date and invoice_to_date and (customer or customer_group)):
        frappe.throw("Please fill all filter fields.")

    # Fetch default receivable account from the Company doctype
    company = frappe.defaults.get_user_default("company")
    default_receivable_account = frappe.db.get_value('Company', company, 'default_receivable_account')

    if not default_receivable_account:
        frappe.throw("Default Receivable Account not set in Company settings.")

    # Determine filters based on whether customer or customer_group is provided
    filters = {
        'voucher_type': ['in', ['Sales Invoice', 'Journal Entry']],
        'posting_date': ['between', [invoice_from_date, invoice_to_date]],
        'account': default_receivable_account,
        'is_cancelled': 0
    }

    if customer:
        filters['party'] = customer
    elif customer_group:
        # Fetch Customers linked with Customer Group
        customers = frappe.get_all('Customer', filters={'customer_group': customer_group}, fields=['name'])
        filters['party'] = ['in', [customer.name for customer in customers]]

    # Fetch GL Entries ordered by posting date descending
    gl_entries = frappe.get_all('GL Entry',
        filters=filters,
        fields=['voucher_type', 'voucher_no', 'party', 'posting_date', 'debit', 'credit', 'voucher_subtype'],
        order_by='posting_date asc'
    )

    # Prepare data for child table
    receipt_details = []
    for entry in gl_entries:
        # Determine amount based on voucher subtype if available
        amount = entry.debit if entry.voucher_subtype == 'Debit Note' else (-entry.credit if entry.voucher_subtype == 'Credit Note' else 0)
        
        if amount != 0:
            receipt_details.append({
                'reference_doctype': entry.voucher_type,
                'reference_voucher': entry.voucher_no,
                'party': entry.party,
                'date': entry.posting_date,
                'total_amount': amount,
                'outstanding_amount': amount,
                'allocated_amount': amount
            })

    return receipt_details







