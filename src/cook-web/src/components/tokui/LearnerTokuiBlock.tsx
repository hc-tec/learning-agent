'use client';

import React, { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Loader2, RefreshCw } from 'lucide-react';
import api from '@/api';
import { Button } from '@/components/ui/Button';
import { toast } from '@/hooks/useToast';
import TokuiRenderer, {
  TokuiInteractionField,
  TokuiResponseValue,
} from './TokuiRenderer';

type LearnerTokuiArtifact = {
  enabled?: boolean;
  tokui_artifact_bid?: string;
  schema_hash?: string;
  dsl?: string;
  interaction_schema?: TokuiInteractionField[];
  validation_status?: string;
  fallback_text?: string;
};

type LearnerTokuiBlockProps = {
  shifuBid: string;
  outlineBid: string;
  previewMode?: boolean;
  className?: string;
  style?: React.CSSProperties;
};

type SaveTokuiResponsesResult = {
  continue_required?: boolean;
  continue_fields?: string[];
};

export default function LearnerTokuiBlock({
  shifuBid,
  outlineBid,
  previewMode = false,
  className,
  style,
}: LearnerTokuiBlockProps) {
  const { t } = useTranslation();
  const [artifact, setArtifact] = useState<LearnerTokuiArtifact | null>(null);
  const [loading, setLoading] = useState(false);
  const [showLoading, setShowLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const loadArtifact = useCallback(
    async (retry = false) => {
      if (!shifuBid || !outlineBid || previewMode) {
        setArtifact(null);
        return;
      }
      setLoading(true);
      setError('');
      try {
        const result = (
          retry
            ? await api.retryLearnerTokui({
                shifu_bid: shifuBid,
                outline_bid: outlineBid,
              })
            : await api.getLearnerTokui({
                shifu_bid: shifuBid,
                outline_bid: outlineBid,
              })
        ) as LearnerTokuiArtifact;
        setArtifact(result?.enabled ? result : null);
      } catch {
        setArtifact({
          enabled: true,
          validation_status: 'failed',
          fallback_text: t('module.chat.tokuiLoadFailed'),
        });
        setError(t('module.chat.tokuiLoadFailed'));
      } finally {
        setLoading(false);
      }
    },
    [outlineBid, previewMode, shifuBid, t],
  );

  useEffect(() => {
    setArtifact(null);
    void loadArtifact(false);
  }, [loadArtifact]);

  useEffect(() => {
    if (!loading) {
      setShowLoading(false);
      return;
    }
    const timer = window.setTimeout(() => setShowLoading(true), 500);
    return () => window.clearTimeout(timer);
  }, [loading]);

  const submitResponses = useCallback(
    async (responses: TokuiResponseValue[]) => {
      if (!artifact?.tokui_artifact_bid || !responses.length || saving) return;
      setSaving(true);
      try {
        const result = (await api.saveLearnerTokuiResponses({
          shifu_bid: shifuBid,
          outline_bid: outlineBid,
          tokui_artifact_bid: artifact.tokui_artifact_bid,
          schema_hash: artifact.schema_hash || '',
          responses,
        })) as SaveTokuiResponsesResult;
        const responseIds = new Set(
          responses.map(response => response.field_id).filter(Boolean),
        );
        const shouldContinue =
          Boolean(result?.continue_required) ||
          (artifact.interaction_schema || []).some(
            field =>
              responseIds.has(field.field_id) &&
              (field.blocking || field.continue_on_submit),
          );
        if (shouldContinue) {
          setSaving(false);
          await loadArtifact(true);
          return;
        }
        toast({ title: t('module.chat.tokuiResponseSaved') });
      } finally {
        setSaving(false);
      }
    },
    [
      artifact?.interaction_schema,
      artifact?.schema_hash,
      artifact?.tokui_artifact_bid,
      loadArtifact,
      outlineBid,
      saving,
      shifuBid,
      t,
    ],
  );

  if (previewMode || (!artifact && !showLoading)) {
    return null;
  }

  const hasRenderableDsl =
    artifact?.enabled &&
    artifact.validation_status === 'validated' &&
    Boolean(artifact.dsl);

  return (
    <section
      className={className}
      style={style}
    >
      <div className='rounded-md border border-[var(--border)] bg-[var(--card)] p-4 shadow-sm'>
        {showLoading && loading ? (
          <div className='flex items-center gap-2 text-sm text-[var(--muted-foreground)]'>
            <Loader2 className='h-4 w-4 animate-spin' />
            {t('module.chat.tokuiGenerating')}
          </div>
        ) : hasRenderableDsl ? (
          <>
            <TokuiRenderer
              dsl={artifact?.dsl}
              interactionSchema={artifact?.interaction_schema || []}
              onSubmitResponses={submitResponses}
            />
            {saving ? (
              <div className='mt-2 flex items-center gap-2 text-xs text-[var(--muted-foreground)]'>
                <Loader2 className='h-3 w-3 animate-spin' />
                {t('module.chat.tokuiSaving')}
              </div>
            ) : null}
          </>
        ) : (
          <div className='space-y-3'>
            <p className='text-sm leading-6 text-[var(--muted-foreground)]'>
              {artifact?.fallback_text ||
                error ||
                t('module.chat.tokuiLoadFailed')}
            </p>
            <Button
              type='button'
              size='sm'
              variant='outline'
              disabled={loading}
              onClick={() => void loadArtifact(true)}
            >
              {loading ? (
                <Loader2 className='h-4 w-4 animate-spin' />
              ) : (
                <RefreshCw className='h-4 w-4' />
              )}
              {t('module.chat.tokuiRetry')}
            </Button>
          </div>
        )}
      </div>
    </section>
  );
}
