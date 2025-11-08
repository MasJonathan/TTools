/*
  ==============================================================================

	WChart.cpp
	Created: 8 Nov 2025 12:45:58pm
	Author:  Jonathan

  ==============================================================================
*/

#include "WChart.h"
#include "../../layout/WFlexLayout.h"
#include "../WLookAndFeel.h"
#include "WChartAxis.h"
#include "WChartViewport.h"

WChart::WChart()
	: _xAxis(new WChartAxis())
	, _yAxis(new WChartAxis())
	, _viewport(new WChartViewport())
{
	addAndMakeVisible(&*_xAxis);
	addAndMakeVisible(&*_yAxis);
	addAndMakeVisible(&*_viewport);

	// auto options = WFlexLayout::Options::vertical_group();
	// options.spacing = 20;
	// setParentLayout(new WFlexLayout(options));
	// _viewport->getLayout().setAnchors({ 0, 0, 0, 0 }).setBorders({ 0, 0, 100, 100 });
	// _xAxis->getLayout().setAnchors({ 1, 0, 0, 0 }).setPivot({ 0.5f, 0.0f }).setBorders({ 0, 0, 0, 0 });
	// _yAxis->getLayout().setAnchors({ 0, 1, 0, 0 }).setPivot({0.0f, 0.5f}).setBorders({ 0, 0, 0, 0 });
}

WChart::~WChart() {
	
}

void WChart::paint(Graphics& g) {
	g.setColour(WLookAndFeel::bgWidgetColour);
	g.fillRoundedRectangle(getLocalBounds().toFloat(), WLookAndFeel::widgetCorner);
	g.setColour(WLookAndFeel::bgWidgetColour.brighter());
	g.drawRoundedRectangle(getLocalBounds().reduced(1).toFloat(), WLookAndFeel::widgetCorner, 1.0f);
}

void WChart::resized() {
	// BaseComponent::resized();
	auto bounds = getLocalBounds();
	auto bRight = bounds.removeFromRight(100);
	bRight.removeFromBottom(100);
	auto bBot = bounds.removeFromBottom(100);
	auto bContent = bounds;

	_viewport->setBounds(bContent);
	_xAxis->setBounds(bBot);
	_yAxis->setBounds(bRight);
}
