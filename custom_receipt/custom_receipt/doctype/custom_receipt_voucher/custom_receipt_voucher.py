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
def fetch_gl_entries(invoice_from_date, invoice_to_date, customer=None, customer_group=None, company=None):
    # Validate input
    if not (invoice_from_date and invoice_to_date and (customer or customer_group)):
        frappe.throw("Please fill all filter fields.")

    if not company:
        company = frappe.defaults.get_user_default("company")

    # Prepare data for child table
    receipt_details = []

    # Determine customer filters
    customer_filters = {}
    if customer:
        customer_filters['name'] = customer
    elif customer_group:
        customer_filters['customer_group'] = customer_group

    # Fetch customers
    customers = frappe.get_all('Customer', filters=customer_filters, fields=['name'])
    customer_list = [c.name for c in customers]

    if not customer_list:
        return receipt_details

    # Fetch Sales Invoices
    sales_invoice_filters = {
        'posting_date': ['between', [invoice_from_date, invoice_to_date]],
        'customer': ['in', customer_list],
        'docstatus': 1,  # Submitted
        'company': company
    }

    sales_invoices = frappe.get_all('Sales Invoice',
        filters=sales_invoice_filters,
        fields=['name', 'customer', 'posting_date', 'grand_total', 'outstanding_amount', 'is_return'],
        order_by='posting_date asc'
    )

    # Process Sales Invoices
    for invoice in sales_invoices:
        # For return invoices, use negative amounts
        if invoice.is_return:
            total_amount = -abs(invoice.grand_total)
            outstanding = -abs(invoice.outstanding_amount)
        else:
            total_amount = invoice.grand_total
            outstanding = invoice.outstanding_amount

        # Only include invoices with outstanding amounts
        if outstanding != 0:
            receipt_details.append({
                'reference_doctype': 'Sales Invoice',
                'reference_voucher': invoice.name,
                'party': invoice.customer,
                'date': invoice.posting_date,
                'total_amount': total_amount,
                'outstanding_amount': outstanding,
                'allocated_amount': outstanding
            })

    # Fetch Journal Entries with the customer as party
    je_filters = {
        'posting_date': ['between', [invoice_from_date, invoice_to_date]],
        'docstatus': 1,
        'company': company
    }

    journal_entries = frappe.db.sql("""
        SELECT DISTINCT
            je.name,
            jea.party,
            je.posting_date,
            je.voucher_type
        FROM `tabJournal Entry` je
        INNER JOIN `tabJournal Entry Account` jea ON je.name = jea.parent
        WHERE je.docstatus = 1
            AND je.posting_date BETWEEN %s AND %s
            AND je.company = %s
            AND jea.party_type = 'Customer'
            AND jea.party IN %s
            AND jea.reference_type IS NULL
        ORDER BY je.posting_date ASC
    """, (invoice_from_date, invoice_to_date, company, customer_list), as_dict=1)

    # Process Journal Entries
    for je in journal_entries:
        # Get the total debit and credit for this customer in this JE
        je_accounts = frappe.db.sql("""
            SELECT
                SUM(debit_in_account_currency) as total_debit,
                SUM(credit_in_account_currency) as total_credit
            FROM `tabJournal Entry Account`
            WHERE parent = %s
                AND party_type = 'Customer'
                AND party = %s
        """, (je.name, je.party), as_dict=1)

        if je_accounts:
            total_debit = je_accounts[0].total_debit or 0
            total_credit = je_accounts[0].total_credit or 0
            amount = total_debit - total_credit

            if amount != 0:
                receipt_details.append({
                    'reference_doctype': 'Journal Entry',
                    'reference_voucher': je.name,
                    'party': je.party,
                    'date': je.posting_date,
                    'total_amount': amount,
                    'outstanding_amount': amount,
                    'allocated_amount': amount
                })

    return receipt_details







