export const shouldHideReadModeContentForLoading = ({
  isLoading,
  hasReadModeItems,
  shouldShowReadModeStreamingDots,
  hasIndependentRuntimeContent = false,
}: {
  isLoading: boolean;
  hasReadModeItems: boolean;
  shouldShowReadModeStreamingDots: boolean;
  hasIndependentRuntimeContent?: boolean;
}) =>
  isLoading &&
  !hasReadModeItems &&
  !shouldShowReadModeStreamingDots &&
  !hasIndependentRuntimeContent;
