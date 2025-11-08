/*
  ==============================================================================

	WChartingView.h
	Created: 8 Nov 2025 10:03:49am
	Author:  Jonathan

  ==============================================================================
*/

#pragma once
#include "widgets/ui/BaseComponent.h"
#include "widgets/ui/WLabel.h"
#include "widgets/ui/chart/WChart.h"

class WLookAndFeel;

class WChartingView : public BaseComponent {
public:

	WChartingView();

	~WChartingView();

	void paint(Graphics& g) override;

	void resized() override;

private:

	WLookAndFeel* _initLnf();

	UPtr<WLookAndFeel> _lnf;
	WLabel _label;
	WChart _chart;
};

