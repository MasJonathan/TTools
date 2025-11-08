#pragma once
#include <JuceHeader.h>


class WChartingView;

class MainComponent  : public juce::Component
{
public:
	MainComponent();
	~MainComponent() override;

	void paint (juce::Graphics&) override;
	void resized() override;

private:
	UPtr<WChartingView> _chartingView;

	JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR (MainComponent)
};
