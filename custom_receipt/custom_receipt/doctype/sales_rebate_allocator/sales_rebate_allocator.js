// Copyright (c) 2024, Aadhil and contributors
// For license information, please see license.txt

frappe.ui.form.on('Sales Rebate Allocator', {
    get_entries: function(frm) {
        frm.clear_table('sales_rebate_allocator_details');
        
        if (!frm.doc.from_date || !frm.doc.to_date) {
            frappe.msgprint(__('Please select both From Date and To Date.'));
            return;
        }

        frappe.show_alert({message:__('Fetching Sales Invoices...'), indicator:'blue'});
        frappe.call({
            method: 'custom_receipt.custom_receipt.doctype.sales_rebate_allocator.sales_rebate_allocator.get_sales_invoices',
            args: {
                from_date: frm.doc.from_date,
                to_date: frm.doc.to_date
            },
            callback: function(r) {
                if (r.message) {
                    r.message.sales_invoices.forEach(function(d) {
                        let row = frm.add_child('sales_rebate_allocator_details');
                        row.sales_invoice = d.sales_invoice;
                        row.customer = d.customer;
                        row.date = d.date;
                        row.amount = d.amount;
                        row.rebate_percentage = d.rebate_percentage;
                        row.rebate_amount = d.rebate_amount;
                    });
                    frm.set_value('total_amount', r.message.total_amount); // Set the total amount
                    frm.refresh_field('sales_rebate_allocator_details');
                    frm.refresh_field('total_amount'); // Refresh total amount field
                }
            }
        });
    }
});

