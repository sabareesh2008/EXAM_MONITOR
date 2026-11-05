-- =========================================================================
-- VSB Exam Watch V2.3 - Centralized Student Examination Allotment Schema
-- Database: PostgreSQL / Supabase
-- =========================================================================

-- 1. Create Allotments Table
CREATE TABLE IF NOT EXISTS public.allotments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    register_number TEXT NOT NULL,
    student_name TEXT,
    department TEXT,
    exam_date DATE NOT NULL,
    session TEXT NOT NULL CHECK (session IN ('FN', 'AN')),
    subject_code TEXT DEFAULT '',
    subject_name TEXT DEFAULT '',
    hall_number TEXT NOT NULL,
    seat_number TEXT DEFAULT 'Check Hall',
    page_number INTEGER,
    source_pdf_url TEXT,
    seating_image TEXT DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    -- Unique constraint for deduplication on upsert
    CONSTRAINT uq_allotment UNIQUE (register_number, exam_date, session, subject_code)
);

-- Ensure seating_image column exists if table was already created
ALTER TABLE public.allotments ADD COLUMN IF NOT EXISTS seating_image TEXT DEFAULT '';

-- 2. Indexes for Ultra-Fast Search Queries
CREATE INDEX IF NOT EXISTS idx_allotments_register_number ON public.allotments(register_number);
CREATE INDEX IF NOT EXISTS idx_allotments_exam_date ON public.allotments(exam_date);
CREATE INDEX IF NOT EXISTS idx_allotments_reg_date ON public.allotments(register_number, exam_date, session);

-- 3. Row-Level Security (RLS) Setup
ALTER TABLE public.allotments ENABLE ROW LEVEL SECURITY;

-- Allow ANY user (including anon on GitHub Pages) to search / read examination allotments
DROP POLICY IF EXISTS "Public Read Allotments" ON public.allotments;
CREATE POLICY "Public Read Allotments"
    ON public.allotments
    FOR SELECT
    TO anon, authenticated
    USING (true);

-- Allow read, insert, and update so automated ingestion works with either anon or service key
DROP POLICY IF EXISTS "Public Manage Allotments" ON public.allotments;
CREATE POLICY "Public Manage Allotments"
    ON public.allotments
    FOR ALL
    TO anon, authenticated, service_role
    USING (true)
    WITH CHECK (true);

-- 4. Auto-update timestamp trigger
CREATE OR REPLACE FUNCTION update_allotments_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_update_allotments_timestamp ON public.allotments;
CREATE TRIGGER trg_update_allotments_timestamp
    BEFORE UPDATE ON public.allotments
    FOR EACH ROW
    EXECUTE FUNCTION update_allotments_timestamp();
