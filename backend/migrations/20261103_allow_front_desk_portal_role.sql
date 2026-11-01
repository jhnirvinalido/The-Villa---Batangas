DO $migration$
DECLARE
    role_column_number smallint;
    role_type_kind "char";
    role_type_schema name;
    role_type_name name;
    role_constraint record;
BEGIN
    SELECT column_info.attnum, type_info.typtype, namespace_info.nspname, type_info.typname
    INTO role_column_number, role_type_kind, role_type_schema, role_type_name
    FROM pg_attribute AS column_info
    JOIN pg_type AS type_info ON type_info.oid = column_info.atttypid
    JOIN pg_namespace AS namespace_info ON namespace_info.oid = type_info.typnamespace
    WHERE column_info.attrelid = 'public.staff_accounts'::regclass
      AND column_info.attname = 'role'
      AND NOT column_info.attisdropped;

    IF role_column_number IS NULL THEN
        RAISE EXCEPTION 'public.staff_accounts.role was not found.';
    END IF;

    IF role_type_kind = 'e' THEN
        EXECUTE format(
            'ALTER TYPE %I.%I ADD VALUE IF NOT EXISTS %L',
            role_type_schema,
            role_type_name,
            'front_desk'
        );
        RETURN;
    END IF;

    FOR role_constraint IN
        SELECT constraint_info.conname
        FROM pg_constraint AS constraint_info
        WHERE constraint_info.conrelid = 'public.staff_accounts'::regclass
          AND constraint_info.contype = 'c'
          AND array_length(constraint_info.conkey, 1) = 1
          AND constraint_info.conkey[1] = role_column_number
    LOOP
        EXECUTE format(
            'ALTER TABLE public.staff_accounts DROP CONSTRAINT %I',
            role_constraint.conname
        );
    END LOOP;

    ALTER TABLE public.staff_accounts
        ADD CONSTRAINT staff_accounts_role_check
        CHECK (
            role IS NOT NULL
            AND role::text IN ('admin', 'staff', 'maintenance', 'front_desk')
        );
END;
$migration$;
