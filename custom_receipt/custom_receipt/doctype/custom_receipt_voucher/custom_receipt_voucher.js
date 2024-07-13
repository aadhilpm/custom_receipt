frappe.ui.form.on('Custom Receipt Voucher', {
    fetch_customer_wise: function(frm) {
        fetchGLData(frm, {
            type: 'customer',
            customer: frm.doc.customer,
            invoice_from_date: frm.doc.invoice_from_date,
            invoice_to_date: frm.doc.invoice_to_date
        });
    },
    customer_group_wise: function(frm) {
        fetchGLData(frm, {
            type: 'customer_group',
            customer_group: frm.doc.customer_group,
            invoice_from_date: frm.doc.invoice_from_date,
            invoice_to_date: frm.doc.invoice_to_date
        });
    },
    calculate_sales_rebate: function(frm) {
        calculateSalesRebate(frm);
    }
});

function fetchGLData(frm, params) {
    if (!params.invoice_from_date || !params.invoice_to_date || (!params.customer && !params.customer_group)) {
        frappe.msgprint(__('Please fill all filter fields.'));
        return;
    }

    let args = {
        invoice_from_date: params.invoice_from_date,
        invoice_to_date: params.invoice_to_date
    };

    if (params.type === 'customer') {
        args.customer = params.customer;
    } else if (params.type === 'customer_group') {
        args.customer_group = params.customer_group;
    }

    frappe.call({
        method: 'custom_receipt.custom_receipt.doctype.custom_receipt_voucher.custom_receipt_voucher.fetch_gl_entries',
        args: args,
        callback: function(r) {
            if (r.message) {
                frm.clear_table('receipt_details');
                // Filter out entries where both total_amount, outstanding_amount, and allocated_amount are zero
                let filtered_entries = r.message.filter(function(d) {
                    return d.total_amount !== 0 || d.outstanding_amount !== 0 || d.allocated_amount !== 0;
                });
                
                $.each(filtered_entries, function(i, d) {
                    let row = frm.add_child('receipt_details');
                    row.reference_doctype = d.reference_doctype;
                    row.reference_voucher = d.reference_voucher;
                    row.party = d.party;
                    row.date = d.date;
                    row.total_amount = d.total_amount;
                    row.outstanding_amount = d.outstanding_amount;
                    row.allocated_amount = d.allocated_amount;
                });
                frm.refresh_field('receipt_details');
            }
        }
    });
}

function calculateSalesRebate(frm) {
    let rebateDetails = {};

    $.each(frm.doc.receipt_details || [], function(i, row) {
        // Initialize the rebate details for the customer if not already done
        if (!rebateDetails[row.party]) {
            rebateDetails[row.party] = {
                total_amount: 0,
                sales_rebate_percentage: row.sales_rebate_percentage || 0
            };
        }
        // Add the total amount for the customer
        rebateDetails[row.party].total_amount += row.total_amount;
    });

    // Clear the existing Addition or Deduction Details table
    frm.clear_table('addition_or_deduction_details');

    // Loop through the calculated rebate details to add entries to the Addition or Deduction Details table
    for (let customer in rebateDetails) {
        let rebate = Math.round((rebateDetails[customer].total_amount * (rebateDetails[customer].sales_rebate_percentage / 100)));
        let row = frm.add_child('addition_or_deduction_details');
        row.account = frm.doc.rebate_account;
        row.customer = customer;
        row.amount = -rebate;
    }
    
    // Refresh the Addition or Deduction Details table field
    frm.refresh_field('addition_or_deduction_details');
}