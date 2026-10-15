BEGIN;

CREATE TABLE departments (
    department_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    department_name VARCHAR(100) NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE employees (
    employee_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    employee_code VARCHAR(20) NOT NULL UNIQUE,
    full_name VARCHAR(150) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    department_id BIGINT REFERENCES departments(department_id),
    manager_id BIGINT REFERENCES employees(employee_id),
    date_joined DATE NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE attendance_records (
    attendance_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    employee_id BIGINT NOT NULL REFERENCES employees(employee_id),
    work_date DATE NOT NULL,
    clock_in TIMESTAMPTZ,
    clock_out TIMESTAMPTZ,
    status VARCHAR(20) NOT NULL,
    work_location VARCHAR(30) NOT NULL DEFAULT 'OFFICE',
    source VARCHAR(50),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_attendance_employee_date
        UNIQUE (employee_id, work_date),

    CONSTRAINT chk_attendance_status
        CHECK (status IN (
            'PRESENT', 'ABSENT', 'LATE',
            'HALF_DAY', 'ON_LEAVE', 'HOLIDAY', 'WEEKEND'
        )),

    CONSTRAINT chk_attendance_location
        CHECK (work_location IN ('OFFICE', 'WFH', 'FIELD')),

    CONSTRAINT chk_attendance_clock
        CHECK (
            (clock_in IS NULL AND clock_out IS NULL)
            OR
            (clock_in IS NOT NULL AND
             (clock_out IS NULL OR clock_out >= clock_in))
        )
);

CREATE TABLE timesheets (
    timesheet_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    employee_id BIGINT NOT NULL REFERENCES employees(employee_id),
    work_date DATE NOT NULL,
    hours_worked NUMERIC(5,2) NOT NULL DEFAULT 0,
    description TEXT,
    submission_status VARCHAR(20) NOT NULL DEFAULT 'DRAFT',
    submitted_at TIMESTAMPTZ,
    approved_at TIMESTAMPTZ,

    CONSTRAINT uq_timesheet_employee_date
        UNIQUE (employee_id, work_date),

    CONSTRAINT chk_timesheet_hours
        CHECK (hours_worked >= 0 AND hours_worked <= 24),

    CONSTRAINT chk_timesheet_status
        CHECK (submission_status IN (
            'DRAFT', 'SUBMITTED', 'APPROVED', 'REJECTED'
        ))
);

CREATE TABLE holidays (
    holiday_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    holiday_date DATE NOT NULL,
    holiday_name VARCHAR(150) NOT NULL,
    region VARCHAR(100) NOT NULL DEFAULT 'Default',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    CONSTRAINT uq_holiday_date_region
        UNIQUE (holiday_date, region)
);

CREATE TABLE leave_requests (
    leave_request_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    employee_id BIGINT NOT NULL REFERENCES employees(employee_id),
    leave_type VARCHAR(50) NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    reason TEXT,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    requested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    reviewed_at TIMESTAMPTZ,

    CONSTRAINT chk_leave_dates
        CHECK (end_date >= start_date),

    CONSTRAINT chk_leave_status
        CHECK (status IN (
            'PENDING', 'APPROVED', 'REJECTED', 'CANCELLED'
        ))
);

CREATE TABLE wfh_requests (
    wfh_request_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    employee_id BIGINT NOT NULL REFERENCES employees(employee_id),
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    reason TEXT,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    requested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    reviewed_at TIMESTAMPTZ,

    CONSTRAINT chk_wfh_dates
        CHECK (end_date >= start_date),

    CONSTRAINT chk_wfh_status
        CHECK (status IN (
            'PENDING', 'APPROVED', 'REJECTED', 'CANCELLED'
        ))
);

CREATE TABLE work_schedules (
    schedule_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    employee_id BIGINT NOT NULL REFERENCES employees(employee_id),
    effective_from DATE NOT NULL,
    effective_to DATE,
    shift_start TIME NOT NULL,
    shift_end TIME NOT NULL,
    workdays JSONB NOT NULL DEFAULT '[1,2,3,4,5]'::JSONB,
    expected_hours NUMERIC(5,2) NOT NULL DEFAULT 8,

    CONSTRAINT chk_schedule_dates
        CHECK (
            effective_to IS NULL OR effective_to >= effective_from
        ),

    CONSTRAINT chk_schedule_hours
        CHECK (expected_hours > 0 AND expected_hours <= 24)
);

CREATE INDEX idx_attendance_employee_date
    ON attendance_records(employee_id, work_date);

CREATE INDEX idx_timesheets_employee_date
    ON timesheets(employee_id, work_date);

CREATE INDEX idx_leave_employee_status
    ON leave_requests(employee_id, status);

CREATE INDEX idx_wfh_employee_status
    ON wfh_requests(employee_id, status);

CREATE INDEX idx_holidays_date_region
    ON holidays(holiday_date, region);

CREATE INDEX idx_schedules_employee_dates
    ON work_schedules(employee_id, effective_from, effective_to);

COMMIT;