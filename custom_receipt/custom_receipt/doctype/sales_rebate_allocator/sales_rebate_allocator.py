# Copyright (c) 2024, Aadhil and Contributors

import frappe
from frappe.model.document import Document

class SalesRebateAllocator(Document):
    def on_submit(self):
        self.create_journal_entry()

    def on_cancel(self):
        self.cancel_journal_entry()

    def create_journal_entry(self):
        customer_rebates = {}
        total_credit = 0
        total_debit = 0

        for row in self.sales_rebate_allocator_details:
            if row.customer not in customer_rebates:
                customer_rebates[row.customer] = 0
            
            customer_rebates[row.customer] += row.rebate_amount

        try:
            je = frappe.get_doc({
                'doctype': 'Journal Entry',
                'posting_date': self.posting_date,
                'cheque_no': self.name,
                'cheque_date': self.posting_date,
                'user_remark': self.remark,
                'accounts': []
            })

            for customer, rebate_amount in customer_rebates.items():
                if rebate_amount == 0:
                    continue

                if rebate_amount > 0:
                    je.append('accounts', {
                        'account': self.accrual_account,
                        'credit_in_account_currency': rebate_amount,
                        'user_remark': f"{customer} Sales Rebate for {self.remark}"
                    })
                    total_credit += rebate_amount

                    je.append('accounts', {
                        'account': self.expense_account,
                        'debit_in_account_currency': rebate_amount,
                        'user_remark': f"{customer} Sales Rebate for {self.remark}"
                    })
                    total_debit += rebate_amount
                else:
                    je.append('accounts', {
                        'account': self.accrual_account,
                        'debit_in_account_currency': abs(rebate_amount),
                        'user_remark': f"{customer} Sales Rebate for {self.remark}"
                    })
                    total_debit += abs(rebate_amount)

                    je.append('accounts', {
                        'account': self.expense_account,
                        'credit_in_account_currency': abs(rebate_amount),
                        'user_remark': f"{customer} Sales Rebate for {self.remark}"
                    })
                    total_credit += abs(rebate_amount)

            je.insert()
            je.submit()

            self.journal_entry = je.name

            if total_credit != total_debit:
                frappe.throw(f"Total Credit ({total_credit}) and Total Debit ({total_debit}) do not match!")

        except frappe.ValidationError as e:
            frappe.throw(f"An error occurred while creating the Journal Entry: {str(e)}")

    def cancel_journal_entry(self):
        journal_entry = frappe.db.get_value('Journal Entry', {'cheque_no': self.name}, 'name')

        if journal_entry:
            je = frappe.get_doc('Journal Entry', journal_entry)
            if je.docstatus == 1:  # Ensure the JE is submitted
                je.cancel()
            else:
                frappe.throw(f"Journal Entry {je.name} is not submitted and cannot be canceled.")
        else:
            frappe.throw(f"No Journal Entry found with Sales Rebate Allocator: {self.name}")

@frappe.whitelist()
def get_sales_invoices(from_date, to_date):
    sales_invoices = frappe.db.get_list('Sales Invoice', 
        filters={
            'posting_date': ['between', [from_date, to_date]],
            'docstatus': 1
        },
        fields=['name', 'customer', 'posting_date', 'grand_total'],
        order_by='posting_date asc'
    )

    filtered_invoices = []
    total_amount = 0

    for invoice in sales_invoices:
        rebate_percentage = frappe.db.get_value('Customer', invoice['customer'], 'custom_rebate_percentage')
        
        if rebate_percentage:
            rebate_amount = invoice['grand_total'] * (rebate_percentage / 100)
            total_amount += rebate_amount

            filtered_invoices.append({
                'sales_invoice': invoice['name'],
                'customer': invoice['customer'],
                'date': invoice['posting_date'],
                'amount': invoice['grand_total'],
                'rebate_percentage': rebate_percentage,
                'rebate_amount': rebate_amount
            })

    return {
        'sales_invoices': filtered_invoices,
        'total_amount': total_amount
    }
