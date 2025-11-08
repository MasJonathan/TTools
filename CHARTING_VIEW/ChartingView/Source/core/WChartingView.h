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

class WLookAndFeel;

class WChartingView : public BaseComponent {
public:

	WChartingView();

	~WChartingView();

	void paint(Graphics& g) override;

private:

	WLookAndFeel* _initLnf();

	UPtr<WLookAndFeel> _lnf;
	WLabel _label;
};

