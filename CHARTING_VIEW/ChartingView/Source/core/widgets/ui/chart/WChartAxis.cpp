/*
  ==============================================================================

	WChartAxis.cpp
	Created: 8 Nov 2025 12:47:24pm
	Author:  Jonathan

  ==============================================================================
*/

#include "WChartAxis.h"
#include "WChartTransform.h"

WChartAxis::WChartAxis(WChartScaleTransform& scaleData) : _scaleData(scaleData) {

}

void WChartAxis::paint(Graphics& g) {
	g.fillAll(Colours::green);
}
