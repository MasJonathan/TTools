/*
  ==============================================================================

	WChartAxis.h
	Created: 8 Nov 2025 12:47:24pm
	Author:  Jonathan

  ==============================================================================
*/

#pragma once
#include "../BaseComponent.h"

class WChartAxis : public BaseComponent {
public:
	WChartAxis(WChartScaleData& scaleData) : _scaleData(scaleData) {

	}

	void paint(Graphics& g) override {
		g.fillAll(Colours::green);
	}

private:
	WChartScaleData& _scaleData;
};


