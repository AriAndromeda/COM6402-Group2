
# US06 – User Access and Audit

## Overview

US06 introduces role-based access control and audit logging
to protect operational changes within HeatShield.

## Authentication and Authorisation

Restricted endpoints require an HTTP Bearer token.

The application stores SHA-256 hashes of access tokens rather
than their original values.

Supported roles:
- staff
- supervisor

Unauthenticated or invalid credentials return HTTP 401.
Authenticated users without the required role receive HTTP 403.

## Protected Operations

| Operation | Endpoint | Roles |
|---|---|---|
| Update support request | PATCH /api/requests/<id> | Staff, Supervisor |
| Delete support request | DELETE /api/requests/<id> | Staff, Supervisor |
| Create cooling centre | POST /api/centres | Staff, Supervisor |
| Create booking | POST /api/bookings | Staff, Supervisor |

Support-request creation remains publicly accessible to
support assistance submissions.

## Audit Logging

Successful protected changes create database audit records
containing:

- Staff user ID
- Action performed
- Resource type
- Resource ID
- Timestamp

Audit records are committed in the same database transaction
as their corresponding operational changes.

## Staff Provisioning

The internal provision_staff() function generates a secure
token using Python's secrets module and stores its SHA-256
hash in the StaffUser database table.

Accounts can be deactivated using the is_active field.
There is no public staff-registration endpoint.

## Testing

The implementation was verified using pytest, covering:

- Missing and invalid credentials
- Role-based access restrictions
- Authorised operations
- Inactive staff accounts
- Audit record creation
- Rejected booking operations
- Database rollback following simulated audit failure
- Staff provisioning and token generation
- Supervisor permissions

Full regression result: 118 tests passed.

## Limitations

- The project does not yet provide a production-ready
  administrative identity-management interface.
- Token rotation and expiry are not implemented.
- The application requires secure HTTPS deployment.
- SQLite audit records are not tamper-proof.
- AI recommendation approval cannot be verified until
  the corresponding functionality is available.
- Publicly accessible read endpoints require a separate
  privacy and data-exposure assessment.
