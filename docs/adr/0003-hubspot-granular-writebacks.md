# 3. Granular CRM Intelligence Writebacks

**Date:** 2026-08-05
**Status:** Accepted

**Context:**
A binary "Valid/Invalid" status is insufficient for RevOps. Sales teams need to know *why* an email failed (e.g., a typo vs. a disabled employee) to take correct operational action. 

**Decision:**
The verification engine will not just output binary states. It will push granular intelligence back to custom HubSpot contact properties using the CRM Batch API.
* `Email Verification Status` (Valid, Invalid, Catch-All)
* `Email Verification Reason` (Syntax, Disposable, No_MX, User_Not_Found, Greylisted)
* `Mailbox Provider` (Google Workspace, Microsoft 365, etc.)
* `Is Role Account` (True/False flag for admin@, info@)

**Consequences:**
* **Positive:** Drastically increases the business value of the tool at zero additional compute cost.
* **Negative:** Requires strict alignment between the Python script outputs and the HubSpot custom property internal values.