import sys

# payroll_crm must be first so its app/ package takes precedence
sys.path.insert(0, "/Users/madhavibhat/payroll_crm")
# External engines appended so they never shadow payroll_crm/app/
sys.path.append("/Users/madhavibhat/payroll_v2")
sys.path.append("/Users/madhavibhat/cps-compliance-platform")
