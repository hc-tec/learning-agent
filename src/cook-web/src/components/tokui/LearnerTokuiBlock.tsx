'use client';

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Loader2, RefreshCw } from 'lucide-react';
import api from '@/api';
import { Button } from '@/components/ui/Button';
import { toast } from '@/hooks/useToast';
import TokuiRenderer, {
  TokuiStreamingRenderer,
  TokuiInteractionField,
  TokuiResponseValue,
} from './TokuiRenderer';
import {
  LearnerTokuiStreamEvent,
  LearnerTokuiStreamHandle,
  streamLearnerTokui,
} from './learnerTokuiStream';

type LearnerTokuiArtifact = {
  enabled?: boolean;
  tokui_artifact_bid?: string;
  schema_hash?: string;
  dsl?: string;
  interaction_schema?: TokuiInteractionField[];
  validation_status?: string;
  fallback_text?: string;
  submitted?: boolean;
  submitted_responses?: TokuiResponseValue[];
  artifact_chain?: LearnerTokuiArtifact[];
  render_nonce?: number;
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

type StreamingPreviewState = {
  streamKey: string;
  chunks: string[];
  complete: boolean;
  status?: string;
};

const artifactListFromResult = (
  result?: LearnerTokuiArtifact | null,
): LearnerTokuiArtifact[] => {
  if (!result || result.enabled === false) return [];
  if (Array.isArray(result.artifact_chain) && result.artifact_chain.length) {
    return result.artifact_chain.filter(Boolean);
  }
  if (result.dsl || result.fallback_text || result.validation_status) {
    return [result];
  }
  return [];
};

const EMPTY_SUBMITTED_RESPONSES: TokuiResponseValue[] = [];

const isValidatedArtifact = (item: LearnerTokuiArtifact) =>
  item.validation_status === 'validated' && Boolean(item.dsl);

const appendFallbackArtifact = (
  previous: LearnerTokuiArtifact[],
  fallbackText: string,
) => {
  const fallback: LearnerTokuiArtifact = {
    enabled: true,
    validation_status: 'failed',
    fallback_text: fallbackText,
  };
  const visibleHistory = previous.filter(isValidatedArtifact);
  return visibleHistory.length ? [...visibleHistory, fallback] : [fallback];
};

export default function LearnerTokuiBlock({
  shifuBid,
  outlineBid,
  previewMode = false,
  className,
  style,
}: LearnerTokuiBlockProps) {
  const { t } = useTranslation();
  const [artifacts, setArtifacts] = useState<LearnerTokuiArtifact[]>([]);
  const [loading, setLoading] = useState(false);
  const [showLoading, setShowLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [continuing, setContinuing] = useState(false);
  const [error, setError] = useState('');
  const savingRef = useRef(false);
  const activeStreamRef = useRef<LearnerTokuiStreamHandle | null>(null);
  const streamRequestSeqRef = useRef(0);
  const [streamingPreview, setStreamingPreview] =
    useState<StreamingPreviewState | null>(null);
  const activeArtifact = artifacts[artifacts.length - 1] || null;

  const closeActiveStream = useCallback(() => {
    activeStreamRef.current?.close();
    activeStreamRef.current = null;
  }, []);

  const loadArtifact = useCallback(
    (retry = false) => {
      if (!shifuBid || !outlineBid || previewMode) {
        closeActiveStream();
        setArtifacts([]);
        setStreamingPreview(null);
        return Promise.resolve(undefined);
      }
      closeActiveStream();
      const requestSeq = streamRequestSeqRef.current + 1;
      streamRequestSeqRef.current = requestSeq;
      setLoading(true);
      setError('');
      setStreamingPreview({
        streamKey: `${outlineBid}:${Date.now()}:${requestSeq}`,
        chunks: [],
        complete: false,
      });

      return new Promise<LearnerTokuiArtifact | undefined>(resolve => {
        const finish = (result?: LearnerTokuiArtifact) => {
          if (requestSeq !== streamRequestSeqRef.current) return;
          activeStreamRef.current = null;
          setLoading(false);
          setContinuing(false);
          resolve(result);
        };

        const handleEvent = (event: LearnerTokuiStreamEvent) => {
          if (requestSeq !== streamRequestSeqRef.current) return;
          if (event.type === 'chunk' && event.tokui) {
            setStreamingPreview(previous => ({
              streamKey:
                previous?.streamKey || `${outlineBid}:${Date.now()}:${requestSeq}`,
              chunks: [...(previous?.chunks || []), event.tokui || ''],
              complete: false,
              status: previous?.status,
            }));
            return;
          }
          if (event.type === 'status') {
            setStreamingPreview(previous => ({
              streamKey:
                previous?.streamKey || `${outlineBid}:${Date.now()}:${requestSeq}`,
              chunks: previous?.chunks || [],
              complete: previous?.complete || false,
              status: event.status,
            }));
            return;
          }
          if (event.type === 'reset') {
            setStreamingPreview({
              streamKey: `${outlineBid}:${Date.now()}:${requestSeq}:repair`,
              chunks: [],
              complete: false,
              status: 'repairing',
            });
            return;
          }
          if (event.type === 'error') {
            const message = event.message || t('module.chat.tokuiLoadFailed');
            setArtifacts(previous =>
              retry && previous.length
                ? appendFallbackArtifact(previous, message)
                : appendFallbackArtifact([], message),
            );
            setStreamingPreview(null);
            setError(message);
            finish();
            return;
          }
          if (event.type !== 'final') return;

          const result = event.artifact as LearnerTokuiArtifact;
          const nextArtifacts = artifactListFromResult(result);
          setArtifacts(previous => {
            if (
              retry &&
              result?.enabled &&
              !Array.isArray(result.artifact_chain) &&
              nextArtifacts.length
            ) {
              const previousBids = new Set(
                nextArtifacts
                  .map(item => item.tokui_artifact_bid)
                  .filter(Boolean),
              );
              return [
                ...previous.filter(
                  item =>
                    isValidatedArtifact(item) &&
                    (!item.tokui_artifact_bid ||
                      !previousBids.has(item.tokui_artifact_bid)),
                ),
                ...nextArtifacts,
              ];
            }
            return nextArtifacts;
          });
          setStreamingPreview(previous =>
            previous ? { ...previous, complete: true } : null,
          );
          window.setTimeout(() => {
            if (requestSeq === streamRequestSeqRef.current) {
              setStreamingPreview(null);
            }
          }, 0);
          finish(result);
        };

        try {
          activeStreamRef.current = streamLearnerTokui({
            shifuBid,
            outlineBid,
            forceRegenerate: retry,
            onEvent: handleEvent,
            onDone: () => {
              if (requestSeq !== streamRequestSeqRef.current) return;
              setStreamingPreview(previous =>
                previous ? { ...previous, complete: true } : null,
              );
            },
            onError: errorEvent => {
              if (requestSeq !== streamRequestSeqRef.current) return;
              const message = t('module.chat.tokuiLoadFailed');
              setArtifacts(previous =>
                retry && previous.length
                  ? appendFallbackArtifact(previous, message)
                  : appendFallbackArtifact([], message),
              );
              setStreamingPreview(null);
              setError(message);
              finish();
              if (process.env.NODE_ENV !== 'test') {
                console.error('[TokUI learner stream error]', errorEvent);
              }
            },
          });
        } catch (streamError) {
          const message = t('module.chat.tokuiLoadFailed');
          setArtifacts(previous =>
            retry && previous.length
              ? appendFallbackArtifact(previous, message)
              : appendFallbackArtifact([], message),
          );
          setStreamingPreview(null);
          setError(message);
          finish();
          if (process.env.NODE_ENV !== 'test') {
            console.error('[TokUI learner stream setup error]', streamError);
          }
        }
      });
    },
    [closeActiveStream, outlineBid, previewMode, shifuBid, t],
  );

  useEffect(() => {
    setArtifacts([]);
    setStreamingPreview(null);
    void loadArtifact(false);
    return () => {
      closeActiveStream();
      streamRequestSeqRef.current += 1;
    };
  }, [closeActiveStream, loadArtifact]);

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
      if (
        !activeArtifact?.tokui_artifact_bid ||
        !responses.length ||
        saving ||
        savingRef.current
      ) {
        return;
      }
      savingRef.current = true;
      const responseSnapshot = responses.map(response => ({ ...response }));
      setSaving(true);
      try {
        const result = (await api.saveLearnerTokuiResponses({
          shifu_bid: shifuBid,
          outline_bid: outlineBid,
          tokui_artifact_bid: activeArtifact.tokui_artifact_bid,
          schema_hash: activeArtifact.schema_hash || '',
          responses,
        })) as SaveTokuiResponsesResult;
        const responseIds = new Set(
          responses.map(response => response.field_id).filter(Boolean),
        );
        const shouldContinue =
          Boolean(result?.continue_required) ||
          (activeArtifact.interaction_schema || []).some(
            field =>
              responseIds.has(field.field_id) &&
              (field.blocking || field.continue_on_submit),
          );
        setArtifacts(previous =>
          previous.map(item =>
            item.tokui_artifact_bid === activeArtifact.tokui_artifact_bid
              ? {
                  ...item,
                  submitted: true,
                  submitted_responses: responseSnapshot,
                }
              : item,
          ),
        );
        if (shouldContinue) {
          setContinuing(true);
          await loadArtifact(true);
          return;
        }
        toast({ title: t('module.chat.tokuiResponseSaved') });
      } catch {
        const message = t('module.chat.tokuiLoadFailed');
        setArtifacts(previous =>
          previous.map(item =>
            item.tokui_artifact_bid === activeArtifact.tokui_artifact_bid
              ? {
                  ...item,
                  submitted: false,
                  submitted_responses: responseSnapshot,
                  render_nonce: (item.render_nonce || 0) + 1,
                }
              : item,
          ),
        );
        setError(message);
        toast({
          title: message,
          variant: 'destructive',
        });
      } finally {
        savingRef.current = false;
        setSaving(false);
      }
    },
    [
      activeArtifact?.interaction_schema,
      activeArtifact?.schema_hash,
      activeArtifact?.tokui_artifact_bid,
      loadArtifact,
      outlineBid,
      saving,
      shifuBid,
      t,
    ],
  );

  if (
    previewMode ||
    (!artifacts.length && !streamingPreview?.chunks.length && !showLoading)
  ) {
    return null;
  }

  return (
    <section
      data-testid='learner-tokui-block'
      className={className}
      style={style}
    >
      <div className='rounded-md border border-[var(--border)] bg-[var(--card)] p-4 shadow-sm'>
        {showLoading &&
        loading &&
        !artifacts.length &&
        !streamingPreview?.chunks.length ? (
          <div className='flex items-center gap-2 text-sm text-[var(--muted-foreground)]'>
            <Loader2 className='h-4 w-4 animate-spin' />
            {t('module.chat.tokuiGenerating')}
          </div>
        ) : (
          <div className='space-y-4'>
            {artifacts.map((item, index) => {
              const hasRenderableDsl =
                item.validation_status === 'validated' &&
                Boolean(item.dsl);
              const isSubmitted = Boolean(item.submitted);
              const isPastArtifact = index < artifacts.length - 1;
              const isReadOnly = isPastArtifact || isSubmitted;
              const submittedResponses =
                item.submitted_responses || EMPTY_SUBMITTED_RESPONSES;
              return (
                <div
                  key={item.tokui_artifact_bid || `tokui-artifact-${index}`}
                  className={index > 0 ? 'border-t border-[var(--border)] pt-4' : ''}
                >
                  {hasRenderableDsl ? (
                    <>
                      <TokuiRenderer
                        key={`${item.tokui_artifact_bid || index}:${
                          item.render_nonce || 0
                        }`}
                        dsl={item.dsl}
                        interactionSchema={item.interaction_schema || []}
                        readOnly={isReadOnly}
                        submittedResponses={submittedResponses}
                        onSubmitResponses={
                          isReadOnly ? undefined : submitResponses
                        }
                      />
                      {isSubmitted ? (
                        <div className='mt-2 text-xs text-[var(--muted-foreground)]'>
                          已提交，答案会用于后续讲解。
                        </div>
                      ) : null}
                    </>
                  ) : (
                    <div className='space-y-3'>
                      <p className='text-sm leading-6 text-[var(--muted-foreground)]'>
                        {item.fallback_text ||
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
              );
            })}
            {streamingPreview?.chunks.length ? (
              <div
                className={
                  artifacts.length
                    ? 'border-t border-[var(--border)] pt-4'
                    : ''
                }
              >
                {streamingPreview.status === 'repairing' ? (
                  <div className='mb-2 flex items-center gap-2 text-xs text-[var(--muted-foreground)]'>
                    <Loader2 className='h-3 w-3 animate-spin' />
                    正在修正互动讲解格式...
                  </div>
                ) : null}
                <TokuiStreamingRenderer
                  streamKey={streamingPreview.streamKey}
                  chunks={streamingPreview.chunks}
                  complete={streamingPreview.complete}
                />
              </div>
            ) : null}
            {saving ? (
              <div className='flex items-center gap-2 text-xs text-[var(--muted-foreground)]'>
                <Loader2 className='h-3 w-3 animate-spin' />
                {continuing
                  ? '已提交，正在根据你的回答继续讲解...'
                  : t('module.chat.tokuiSaving')}
              </div>
            ) : null}
            {showLoading && loading && artifacts.length ? (
              <div className='flex items-center gap-2 text-xs text-[var(--muted-foreground)]'>
                <Loader2 className='h-3 w-3 animate-spin' />
                正在准备后续讲解...
              </div>
            ) : null}
          </div>
        )}
      </div>
    </section>
  );
}
