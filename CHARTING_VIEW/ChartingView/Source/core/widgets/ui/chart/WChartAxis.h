/*
  ==============================================================================

	WChartAxis.h
	Created: 8 Nov 2025 12:47:24pm
	Author:  Jonathan

  ==============================================================================
*/

#pragma once
#include "../BaseComponent.h"

class WChartScaleTransform;

class WChartAxis : public BaseComponent {
public:
	WChartAxis(WChartScaleTransform& scaleData);

	void paint(Graphics& g) override;

private:
	WChartScaleTransform& _scaleData;
};


