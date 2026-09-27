"""Small Salesforce metadata archive used by parser and pipeline tests."""

import io
import zipfile


CUSTOM_OBJECT_XML = """<?xml version="1.0" encoding="UTF-8"?>
<CustomObject xmlns="http://soap.sforce.com/2006/04/metadata">
  <fullName>Invoice__c</fullName>
  <label>Invoice</label>
  <pluralLabel>Invoices</pluralLabel>
  <fields>
    <fullName>Account__c</fullName>
    <label>Account</label>
    <type>Lookup</type>
    <referenceTo>Account</referenceTo>
  </fields>
  <fields>
    <fullName>Status__c</fullName>
    <label>Status</label>
    <type>Text</type>
    <required>true</required>
  </fields>
</CustomObject>
"""

FLOW_XML = """<?xml version="1.0" encoding="UTF-8"?>
<Flow xmlns="http://soap.sforce.com/2006/04/metadata">
  <label>Update Invoice</label>
  <processType>AutoLaunchedFlow</processType>
  <status>Active</status>
  <recordUpdates>
    <object>Invoice__c</object>
    <inputAssignments><field>Status__c</field></inputAssignments>
  </recordUpdates>
</Flow>
"""

PERMISSION_SET_XML = """<?xml version="1.0" encoding="UTF-8"?>
<PermissionSet xmlns="http://soap.sforce.com/2006/04/metadata">
  <label>Invoice User</label>
  <objectPermissions><object>Invoice__c</object></objectPermissions>
  <fieldPermissions><field>Invoice__c.Status__c</field></fieldPermissions>
  <classAccesses><apexClass>InvoiceService</apexClass></classAccesses>
  <flowAccesses><flow>Update_Invoice</flow></flowAccesses>
</PermissionSet>
"""

APEX_CLASS = """public with sharing class InvoiceService {
  public static List<Invoice__c> loadInvoices() {
    return [SELECT Id, Status__c FROM Invoice__c];
  }
}
"""

APEX_TRIGGER = """trigger InvoiceTrigger on Invoice__c (before update) {
  InvoiceService.loadInvoices();
}
"""


def build_metadata_zip() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("unpackaged/objects/Invoice__c.object", CUSTOM_OBJECT_XML)
        archive.writestr("unpackaged/classes/InvoiceService.cls", APEX_CLASS)
        archive.writestr("unpackaged/triggers/InvoiceTrigger.trigger", APEX_TRIGGER)
        archive.writestr("unpackaged/flows/Update_Invoice.flow", FLOW_XML)
        archive.writestr(
            "unpackaged/permissionsets/Invoice_User.permissionset",
            PERMISSION_SET_XML,
        )
        archive.writestr("unpackaged/package.xml", "<Package />")
    return buffer.getvalue()
